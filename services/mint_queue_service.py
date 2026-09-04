"""Mint-queue admission and eligibility records, without block construction."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from content import CONTENT_TYPE_TEXT, STORAGE_STATUS_LOCAL, STORAGE_STATUS_MISSING, STORAGE_STATUS_REMOTE, STORAGE_STATUS_VERIFIED, TEXT_MIME_TYPE, resolve_local_path, verify_content_object_payload
from originality_certificate import validate_certificate_for_submission
from submission import APPROVED, HARD_REJECTED, MINTED, QUEUED
from utils import extract_text


@dataclass
class MintQueueState:
    submissions: list
    content_objects: list
    originality_certificates: list
    mint_queue: list


class MintQueueService:
    """Stateless queue rules over authoritative lists supplied per call."""

    @staticmethod
    def canonical_mint_order_key(certificate):
        """Return the Public Testnet v1 order key for a certified submission.

        Each component is a canonical SHA-256 hexadecimal identifier from the
        validated certificate. The certificate ID includes the submission
        identity and is the collision-resistant final tie-breaker.
        """
        if certificate is None:
            raise ValueError("An originality certificate is required for canonical mint ordering.")
        return (
            str(certificate.content_hash).lower(),
            str(certificate.vote_hash).lower(),
            str(certificate.certificate_id).lower(),
        )

    @staticmethod
    def _submission(state, storage, submission_id):
        return storage.get_submission(submission_id, state.submissions)

    @staticmethod
    def _content_by_hash(state, storage, content_hash):
        return storage.get_content_object_by_hash(content_hash, state.content_objects)

    @staticmethod
    def _content_by_id(state, storage, content_id):
        return storage.get_content_object(content_id, state.content_objects)

    @staticmethod
    def _certificate(state, storage, submission_id):
        return storage.get_certificate_for_submission(submission_id, state.originality_certificates)

    def add(self, state, storage, submission_id, require_certificate):
        submission = self._submission(state, storage, submission_id)
        if not submission: raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == HARD_REJECTED: raise ValueError("Hard rejected submissions cannot enter the mint queue.")
        if submission.status != APPROVED: raise ValueError("Only approved submissions can be added to the mint queue.")
        if submission.mint_blocked: raise ValueError(submission.mint_block_reason or "Submission is blocked from minting.")
        require_certificate(submission)
        if storage.mint_queue_contains(submission_id, state.mint_queue): raise ValueError("Submission is already in the mint queue.")
        state.mint_queue.append(submission_id)
        submission.transition_to(QUEUED)
        return submission

    def record(self, storage, submission, *, content_object=None, certificate=None, network_name, extract_text_func=extract_text):
        record = submission.to_dict()
        record.update({"submission_status": submission.status, "certificate_status": "missing" if certificate is None else "valid", "content_status": STORAGE_STATUS_MISSING, "storage_status": STORAGE_STATUS_MISSING, "content_metadata_missing": True, "missing_fields": [], "mintable": False, "mint_block_reason": None, "download_url": None, "originality_score": certificate.originality_score if certificate else None, "mint_blocked": submission.mint_blocked, "mint_blocked_at": submission.mint_blocked_at, "mint_blocked_by": submission.mint_blocked_by, "mint_block_notes": submission.mint_block_notes})
        if certificate: record["certificate_id"] = certificate.certificate_id
        if submission.mint_blocked:
            record.update(mint_block_reason=submission.mint_block_reason or "mint_blocked_manually", certificate_status="blocked"); return record
        if submission.status == MINTED: record["mint_block_reason"] = "already_minted"; record["missing_fields"].append("status"); return record
        if submission.status != QUEUED: record["mint_block_reason"] = "submission_not_approved"; record["missing_fields"].append("status"); return record
        if certificate is None: record["mint_block_reason"] = "certificate_missing"; record["missing_fields"].append("certificate_id"); return record
        try: validate_certificate_for_submission(certificate, submission, network_name=network_name)
        except ValueError as exc:
            message = str(exc).lower(); record.update(certificate_status="invalid", mint_block_reason="certificate_content_hash_mismatch" if "content_hash" in message or "content_id" in message else "unknown_error", validation_error=str(exc)); record["missing_fields"].append("certificate"); return record
        if content_object is None:
            record["mint_block_reason"] = "content_metadata_missing"; record["missing_fields"].extend(["content_hash", "content_id", "mime_type", "content_type"]); return record
        record.update(content_metadata_missing=False, content_id=content_object.content_id, content_type=content_object.content_type, mime_type=content_object.mime_type, content_status=content_object.storage_status, storage_status=content_object.storage_status)
        if content_object.storage_status in {STORAGE_STATUS_LOCAL, STORAGE_STATUS_VERIFIED}: record["download_url"] = f"/content/{content_object.content_hash}"
        if content_object.storage_status == STORAGE_STATUS_REMOTE: record["mint_block_reason"] = "content_payload_missing"; record["missing_fields"].append("content_payload"); return record
        if content_object.storage_status == STORAGE_STATUS_MISSING: record["mint_block_reason"] = "content_metadata_missing"; record["missing_fields"].append("content_payload"); return record
        verification = verify_content_object_payload(content_object, data_dir=storage.data_dir)
        if not verification["verified"]:
            error = str(verification.get("error") or "").lower()
            if error == "legacy_unverifiable": record.update(mintable=True, mint_block_reason=None); return record
            record["mint_block_reason"] = "content_payload_missing" if error == "missing_file" else "content_hash_mismatch" if error in {"hash_mismatch", "file_size_mismatch"} else "content_not_verified"; record["missing_fields"].append("content_payload"); record["verification_error"] = verification.get("error"); return record
        record.update(mintable=True, mint_block_reason=None, missing_fields=[], certificate_status="valid")
        if not (content_object.mime_type == TEXT_MIME_TYPE or content_object.content_type == CONTENT_TYPE_TEXT) and not str(submission.text_content or "").strip():
            file_path = resolve_local_path(content_object.local_path, data_dir=storage.data_dir)
            if not str(extract_text_func(file_path) if file_path and os.path.isfile(file_path) else "").strip(): record.update(mintable=False, mint_block_reason="no_text_content_extracted"); record["missing_fields"].append("text_content")
        return record

    def evaluate(self, state, storage, submission_id, network_name, extract_text_func=extract_text):
        submission = self._submission(state, storage, submission_id)
        if submission is None:
            return {"submission_id": submission_id, "submission_status": None, "certificate_status": "missing", "content_status": STORAGE_STATUS_MISSING, "storage_status": STORAGE_STATUS_MISSING, "mintable": False, "mint_block_reason": "submission_not_found", "missing_fields": ["submission"], "content_metadata_missing": True, "mint_blocked": False, "mint_blocked_at": None, "mint_blocked_by": None, "mint_block_notes": None, "download_url": None}
        content = self._content_by_hash(state, storage, submission.content_hash) if submission.content_hash else None
        content = content or (self._content_by_id(state, storage, submission.content_id) if submission.content_id else None)
        record = self.record(storage, submission, content_object=content, certificate=self._certificate(state, storage, submission_id), network_name=network_name, extract_text_func=extract_text_func)
        if submission.status == QUEUED and record.get("mint_block_reason") == "certificate_missing": submission.status = APPROVED; record["submission_status"] = APPROVED
        return record

    def record_order_key(self, state, storage, record):
        """Sort ready records by the consensus order, with non-ready records last.

        The fallback is presentation-only: non-ready records are never selected
        for a block and therefore cannot affect canonical mint selection.
        """
        submission_id = str(record.get("submission_id") or "")
        if (
            record.get("submission_status") == QUEUED
            and record.get("certificate_status") == "valid"
            and not record.get("mint_blocked")
        ):
            certificate = self._certificate(state, storage, submission_id)
            if certificate is not None:
                return (0, *self.canonical_mint_order_key(certificate))
        return (1, submission_id.lower())

    def list(self, state, storage, *, network_name, include_blocked=True, mintable_only=False, extract_text_func=extract_text):
        records = [self.evaluate(state, storage, submission_id, network_name, extract_text_func) for submission_id in state.mint_queue]
        records.sort(key=lambda record: self.record_order_key(state, storage, record))
        return [record for record in records if (not mintable_only or record.get("mintable")) and (include_blocked or record.get("mintable"))]

    def block(self, state, storage, submission_id, reason, notes=None, blocked_by=None):
        submission = self._submission(state, storage, submission_id)
        if submission is None: raise ValueError(f"Submission not found: {submission_id}")
        if submission.status == MINTED: raise ValueError("Minted submissions cannot be blocked from minting.")
        submission.mint_blocked, submission.mint_block_reason, submission.mint_blocked_at, submission.mint_blocked_by, submission.mint_block_notes = True, (reason or "mint_blocked_manually").strip() or "mint_blocked_manually", time.time(), blocked_by, notes
        return submission

    def unblock(self, state, storage, submission_id):
        submission = self._submission(state, storage, submission_id)
        if submission is None: raise ValueError(f"Submission not found: {submission_id}")
        submission.mint_blocked = False; submission.mint_block_reason = None; submission.mint_blocked_at = None; submission.mint_blocked_by = None; submission.mint_block_notes = None
        return submission

    def remove_invalid(self, state, storage, require_certificate):
        valid, removed = [], []
        for submission_id in state.mint_queue:
            submission = self._submission(state, storage, submission_id)
            try: ready = submission and submission.status == QUEUED and require_certificate(submission)
            except ValueError: ready = False
            if ready: valid.append(submission_id)
            else:
                if submission and submission.status == QUEUED: submission.status = APPROVED
                if submission and not self._certificate(state, storage, submission.submission_id): submission.certificate_id = None
                removed.append(submission_id)
        state.mint_queue[:] = valid
        return removed
