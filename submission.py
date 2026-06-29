import time
import uuid
from dataclasses import dataclass, field


PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
MINTED = "minted"

VOTE_ORIGINAL = "original"
VOTE_NOT_ORIGINAL = "not_original"
VOTE_UNSURE = "unsure"
VOTE_TYPES = {VOTE_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_UNSURE}

SUBMISSION_STATUSES = {PENDING, APPROVED, REJECTED, MINTED}
VALID_STATUS_TRANSITIONS = {
    PENDING: {APPROVED, REJECTED},
    APPROVED: {MINTED},
    REJECTED: set(),
    MINTED: set(),
}


@dataclass
class Submission:
    image_path: str
    text_content: str
    submitter: str
    status: str = PENDING
    submission_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.status not in SUBMISSION_STATUSES:
            raise ValueError(f"Invalid submission status: {self.status}")

    def transition_to(self, new_status):
        if new_status not in SUBMISSION_STATUSES:
            raise ValueError(f"Invalid submission status: {new_status}")
        if new_status not in VALID_STATUS_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid submission status transition: {self.status} -> {new_status}")

        self.status = new_status
        return self

    def to_dict(self):
        return {
            "submission_id": self.submission_id,
            "image_path": self.image_path,
            "text_content": self.text_content,
            "submitter": self.submitter,
            "status": self.status,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            submission_id=data.get("submission_id") or data.get("id") or uuid.uuid4().hex,
            image_path=data.get("image_path") or data.get("image") or "",
            text_content=data.get("text_content") or data.get("text") or "",
            submitter=data.get("submitter") or data.get("miner") or "",
            status=data.get("status", PENDING),
            created_at=data.get("created_at", time.time()),
        )
