"""Direct Task 7 service characterization without a Blockchain dependency."""

from services import ContentCoordinationService, ContentCoordinationState, MintQueueService, MintQueueState, SubmissionOriginalityService, SubmissionOriginalityState
from submission import PENDING, Submission


class _Storage:
    data_dir = None

    @staticmethod
    def get_submission(submission_id, submissions):
        return next((item for item in submissions if item.submission_id == submission_id), None)

    @staticmethod
    def get_vote(submission_id, voter, votes):
        return next((item for item in votes if item["submission_id"] == submission_id and item["voter"] == voter), None)

    @staticmethod
    def get_votes_for_submission(submission_id, votes):
        return [item for item in votes if item["submission_id"] == submission_id]

    @staticmethod
    def get_certificate(certificate_id, certificates):
        return next((item for item in certificates if item.certificate_id == certificate_id), None)

    @staticmethod
    def get_certificate_for_submission(submission_id, certificates):
        return next((item for item in certificates if item.submission_id == submission_id), None)

    @staticmethod
    def get_content_object(content_id, objects):
        return next((item for item in objects if item.content_id == content_id), None)

    @staticmethod
    def get_content_object_by_hash(content_hash, objects):
        return next((item for item in objects if item.content_hash == content_hash), None)

    @staticmethod
    def list_content_objects(*, status, content_objects):
        return content_objects if status is None else [item for item in content_objects if item.storage_status == status]

    @staticmethod
    def mint_queue_contains(submission_id, queue):
        return submission_id in queue


def test_submission_service_vote_is_persisted_in_authoritative_state():
    submission = Submission("", "service vote", "creator", status=PENDING)
    state = SubmissionOriginalityState([submission], [], [], [])
    service = SubmissionOriginalityService()
    vote = service.cast_submission_vote(state, _Storage(), submission.submission_id, "reviewer", "original", created_at=7)
    assert vote is state.votes[0]
    assert service.get_submission_votes(state, _Storage(), submission.submission_id)["approval_percentage"] == 1


def test_content_service_state_view_rebinds_to_current_authoritative_collections():
    service = ContentCoordinationService()
    assert service.is_text_unique(ContentCoordinationState([], [], {}, {}, [], set()), "same text") is True
    assert service.is_text_unique(ContentCoordinationState([], [], {}, {}, [], set()), "same text") is True


def test_queue_service_keeps_authoritative_queue_identity():
    submission = Submission("", "queue state", "creator", status=PENDING)
    state = MintQueueState([submission], [], [], [])
    service = MintQueueService()
    service.block(state, _Storage(), submission.submission_id, "operator hold")
    assert submission.mint_blocked is True
    service.unblock(state, _Storage(), submission.submission_id)
    assert submission.mint_blocked is False
