import hashlib
import os
import time
import uuid
from dataclasses import dataclass, field

from content import calculate_content_id


PENDING = "pending"
APPROVED = "approved"
QUEUED = "queued"
REJECTED = "rejected"
HARD_REJECTED = "hard_rejected"
MINTED = "minted"

VOTE_ORIGINAL = "original"
VOTE_NOT_ORIGINAL = "not_original"
VOTE_UNSURE = "unsure"
VOTE_TYPES = {VOTE_ORIGINAL, VOTE_NOT_ORIGINAL, VOTE_UNSURE}

SUBMISSION_STATUSES = {PENDING, APPROVED, QUEUED, REJECTED, HARD_REJECTED, MINTED}
VALID_STATUS_TRANSITIONS = {
    PENDING: {APPROVED, REJECTED, HARD_REJECTED},
    APPROVED: {QUEUED, HARD_REJECTED},
    QUEUED: {MINTED, HARD_REJECTED},
    REJECTED: set(),
    HARD_REJECTED: set(),
    MINTED: set(),
}


def calculate_submission_content_hash(image_path="", text_content="", submitter=""):
    content_hash = hashlib.sha256()

    if image_path and os.path.isfile(image_path):
        with open(image_path, "rb") as image_file:
            for chunk in iter(lambda: image_file.read(8192), b""):
                content_hash.update(chunk)
    else:
        content_hash.update((image_path or "").encode("utf-8"))

    content_hash.update(b"\0")
    content_hash.update((text_content or "").strip().encode("utf-8"))
    content_hash.update(b"\0")
    content_hash.update((submitter or "").strip().encode("utf-8"))
    return content_hash.hexdigest()


@dataclass
class Submission:
    image_path: str
    text_content: str
    submitter: str
    status: str = PENDING
    submission_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    hard_reject_reason: str | None = None
    content_hash: str | None = None
    content_id: str | None = None
    certificate_id: str | None = None

    def __post_init__(self):
        if self.status not in SUBMISSION_STATUSES:
            raise ValueError(f"Invalid submission status: {self.status}")
        if not self.content_hash:
            self.content_hash = calculate_submission_content_hash(
                self.image_path,
                self.text_content,
                self.submitter,
            )
        if not self.content_id and self.content_hash:
            self.content_id = calculate_content_id(self.content_hash)
        elif self.content_id is not None and self.content_hash and self.content_id != calculate_content_id(self.content_hash):
            raise ValueError("content_id does not match content_hash.")

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
            "hard_reject_reason": self.hard_reject_reason,
            "content_hash": self.content_hash,
            "content_id": self.content_id,
            "certificate_id": self.certificate_id,
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
            hard_reject_reason=data.get("hard_reject_reason"),
            content_hash=data.get("content_hash"),
            content_id=data.get("content_id"),
            certificate_id=data.get("certificate_id"),
        )
