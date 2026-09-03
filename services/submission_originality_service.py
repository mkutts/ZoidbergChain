"""Submission, voting, and originality-certificate transitions."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from config import ACTIVE_USER_PERCENT_FOR_MIN_VOTES, MIN_VOTE_FLOOR, NETWORK_NAME, ORIGINALITY_APPROVAL_THRESHOLD, VOTING_WINDOW_HOURS
from originality_certificate import OriginalityCertificate, validate_certificate_for_submission
from submission import APPROVED, HARD_REJECTED, MINTED, PENDING, QUEUED, REJECTED, VOTE_NOT_ORIGINAL, VOTE_ORIGINAL, VOTE_TYPES, VOTE_UNSURE


@dataclass
class SubmissionOriginalityState:
    submissions: list
    votes: list
    originality_certificates: list
    mint_queue: list


class SubmissionOriginalityService:
    """Stateless persisted-record transitions; persistence stays with the caller."""

    @staticmethod
    def get_submission(state, storage, submission_id):
        return storage.get_submission(submission_id, state.submissions)

    @staticmethod
    def get_certificate(state, storage, certificate_id):
        return storage.get_certificate(certificate_id, state.originality_certificates)

    @staticmethod
    def get_certificate_for_submission(state, storage, submission_id):
        return storage.get_certificate_for_submission(submission_id, state.originality_certificates)

    def update_submission_status(self, state, storage, submission_id, new_status):
        submission = self.get_submission(state, storage, submission_id)
        if not submission: raise ValueError(f"Submission not found: {submission_id}")
        return submission.transition_to(new_status)

    def hard_reject_submission(self, state, storage, submission_id, reason):
        submission = self.get_submission(state, storage, submission_id)
        if not submission: raise ValueError(f"Submission not found: {submission_id}")
        if not reason: raise ValueError("Hard reject reason is required.")
        submission.hard_reject_reason = reason
        submission.transition_to(HARD_REJECTED)
        state.mint_queue[:] = [item for item in state.mint_queue if item != submission_id]
        return submission

    @staticmethod
    def record_vote(state, voter, submission_id=None, created_at=None):
        vote = {"voter": voter, "submission_id": submission_id, "vote_type": None, "created_at": created_at if created_at is not None else time.time()}
        state.votes.append(vote)
        return vote

    def is_submission_voting_locked(self, state, storage, submission):
        return submission.status in {APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED} or self.get_certificate_for_submission(state, storage, submission.submission_id) is not None

    def cast_submission_vote(self, state, storage, submission_id, voter, vote_type, created_at=None):
        submission = self.get_submission(state, storage, submission_id)
        if not submission: raise ValueError(f"Submission not found: {submission_id}")
        if vote_type not in VOTE_TYPES: raise ValueError(f"Invalid vote type: {vote_type}")
        if voter == submission.submitter: raise ValueError("Submission creator cannot vote on their own submission.")
        if storage.get_vote(submission_id, voter, state.votes): raise ValueError("Wallet has already voted on this submission.")
        if self.is_submission_voting_locked(state, storage, submission): raise ValueError("Finalized or certified submissions cannot receive votes.")
        vote = self.record_vote(state, voter, submission_id, created_at)
        vote["vote_type"] = vote_type
        return vote

    def get_submission_votes(self, state, storage, submission_id):
        if not self.get_submission(state, storage, submission_id): raise ValueError(f"Submission not found: {submission_id}")
        votes = storage.get_votes_for_submission(submission_id, state.votes)
        original = sum(v.get("vote_type") == VOTE_ORIGINAL for v in votes)
        not_original = sum(v.get("vote_type") == VOTE_NOT_ORIGINAL for v in votes)
        unsure = sum(v.get("vote_type") == VOTE_UNSURE for v in votes)
        decisive = original + not_original
        return {"submission_id": submission_id, "votes": votes, "counts": {VOTE_ORIGINAL: original, VOTE_NOT_ORIGINAL: not_original, VOTE_UNSURE: unsure}, "approval_percentage": original / decisive if decisive else 0}

    def link_certificates_to_submissions(self, state, storage):
        changed = False
        for certificate in state.originality_certificates:
            submission = self.get_submission(state, storage, certificate.submission_id)
            if submission and submission.certificate_id != certificate.certificate_id:
                submission.certificate_id = certificate.certificate_id; changed = True
        return changed

    @staticmethod
    def calculate_minimum_votes_required(active_users):
        return max(MIN_VOTE_FLOOR, math.ceil(active_users * ACTIVE_USER_PERCENT_FOR_MIN_VOTES))

    def get_voting_threshold(self, active_user_count, lookback_days, now=None):
        active_users = active_user_count(lookback_days=lookback_days, now=now)
        return {"active_users": active_users, "minimum_votes": self.calculate_minimum_votes_required(active_users), "vote_floor": MIN_VOTE_FLOOR, "active_percentage": ACTIVE_USER_PERCENT_FOR_MIN_VOTES}

    def build_certificate(self, state, storage, submission, approved_at, network_name, issuing_node_id, voting_threshold):
        votes = self.get_submission_votes(state, storage, submission.submission_id)
        return OriginalityCertificate.from_approved_submission(submission, votes["votes"], voting_threshold(now=approved_at)["minimum_votes"], network_name, issuing_node_id, approved_at=approved_at)

    def create_certificate(self, state, storage, submission_id, *, approved_at=None, network_name=NETWORK_NAME, issuing_node_id, allow_pending=False, promote_content, save=None, voting_threshold):
        submission = self.get_submission(state, storage, submission_id)
        if not submission: raise ValueError(f"Submission not found: {submission_id}")
        statuses = {APPROVED, QUEUED} | ({PENDING} if allow_pending else set())
        if submission.status not in statuses: raise ValueError("Only approved unminted submissions can receive originality certificates.")
        existing = self.get_certificate_for_submission(state, storage, submission_id)
        if existing:
            submission.certificate_id = existing.certificate_id
            if save: save()
            return existing
        promote_content(submission)
        approved_at = time.time() if approved_at is None else approved_at
        certificate = self.build_certificate(state, storage, submission, approved_at, network_name, issuing_node_id, voting_threshold)
        validate_certificate_for_submission(certificate, submission, network_name=network_name, allowed_submission_statuses=statuses)
        state.originality_certificates.append(certificate); submission.certificate_id = certificate.certificate_id
        if save: save()
        return certificate
