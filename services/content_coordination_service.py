"""Content-object and local media-cache coordination.

The immutable media carried by a Protocol v1 block remains authoritative.  This
service only coordinates the node-local cache and persisted content metadata.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from block import Block, PROTOCOL_V1_BLOCK_VERSION
from content import (
    CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED, CONTENT_TYPE_TEXT, HASH_SCHEME_LEGACY,
    HASH_SCHEME_SHA256_TEXT, HASH_SCHEME_UNKNOWN, TEXT_MIME_TYPE, ContentObject,
    _validate_content_type, compute_text_content_hash, content_object_from_submission_data,
    guess_mime_type, load_content_bytes, resolve_declared_payload_hash,
    resolve_local_path, resolve_payload_hash, sanitize_original_filename,
    store_content_bytes, validate_caption, validate_text_content,
    verify_content_object_payload,
)
from submission import PENDING, Submission
from utils import hash_image


@dataclass
class ContentCoordinationState:
    submissions: list
    content_objects: list
    text_validation_cache: dict
    image_validation_cache: dict
    texts: list
    image_hashes: set


class ContentCoordinationService:
    """Stateless transitions over caller-owned content and submission state."""

    @staticmethod
    def _block_field(block, field_name, default=None):
        return block.get(field_name, default) if isinstance(block, dict) else getattr(block, field_name, default)

    @classmethod
    def is_protocol_v1_block_payload(cls, block):
        return cls._block_field(block, "block_version") == PROTOCOL_V1_BLOCK_VERSION

    @staticmethod
    def get_content_object(state, storage, content_id):
        return storage.get_content_object(content_id, state.content_objects)

    @staticmethod
    def get_content_object_by_hash(state, storage, content_hash):
        return storage.get_content_object_by_hash(content_hash, state.content_objects)

    @staticmethod
    def list_content_objects(state, storage, status=None):
        return storage.list_content_objects(status=status, content_objects=state.content_objects)

    def is_image_unique(self, state, image_path):
        if image_path in state.image_validation_cache:
            new_hash = state.image_validation_cache[image_path]
        else:
            new_hash = hash_image(image_path)
            state.image_validation_cache[image_path] = new_hash
        if new_hash in state.image_hashes:
            return False
        state.image_hashes.add(new_hash)
        return True

    def is_text_unique(self, state, text_content):
        normalized_text = re.sub(r"[^\w\s]", "", text_content).strip().lower()
        if normalized_text in state.text_validation_cache:
            return state.text_validation_cache[normalized_text]
        if normalized_text in state.texts:
            state.text_validation_cache[normalized_text] = False
            return False
        state.text_validation_cache[normalized_text] = True
        state.texts.append(normalized_text)
        return True

    def is_meme_original(self, state, image_path, text_content):
        image_hash = hash_image(image_path)
        if image_hash in state.image_hashes:
            return False
        return self.is_text_unique(state, text_content)

    def _build_content_object_for_submission(self, state, storage, network_name, submission, image_path="", text_content="", storage_status=None):
        try:
            return content_object_from_submission_data({
                "submission_id": submission.submission_id, "image_path": image_path,
                "text_content": text_content, "submitter": submission.submitter,
                "created_at": submission.created_at, "content_hash": submission.content_hash,
                "content_id": submission.content_id, "certificate_id": submission.certificate_id,
            }, network_name=network_name, storage_status=storage_status, data_dir=storage.data_dir)
        except ValueError:
            return None

    @staticmethod
    def _apply_stored_content_to_object(storage, content_object, stored_content, *, submission_id=None, text_content=""):
        metadata = dict(content_object.metadata or {})
        if stored_content.get("byte_hash"):
            metadata["byte_hash"] = stored_content["byte_hash"]
        if stored_content.get("original_filename"):
            metadata["original_filename"] = stored_content["original_filename"]
        if submission_id:
            metadata["submission_id"] = submission_id
        content_object.mime_type = stored_content["mime_type"]
        content_object.file_size_bytes = stored_content["file_size_bytes"]
        content_object.storage_status = stored_content["storage_status"]
        content_object.local_path = stored_content["local_path"]
        content_object.hash_scheme = stored_content.get("hash_scheme", content_object.hash_scheme)
        if stored_content.get("file_name"):
            content_object.file_name = stored_content["file_name"]
        if text_content and not content_object.text_content:
            content_object.text_content = text_content
        if text_content and not content_object.caption:
            content_object.caption = text_content
        content_object.metadata = metadata
        verification = verify_content_object_payload(content_object, data_dir=storage.data_dir)
        content_object.hash_scheme, content_object.verified_at, content_object.verification_error = verification["hash_scheme"], verification["verified_at"], verification["error"]
        return content_object

    def ensure_content_object_for_submission(self, state, storage, network_name, submission, image_path="", text_content="", stored_content=None, storage_status=None):
        content_object = self.get_content_object_by_hash(state, storage, submission.content_hash)
        if content_object:
            if submission.content_id and submission.content_id != content_object.content_id:
                raise ValueError("content_id does not match content_hash.")
            if not submission.content_id:
                submission.content_id = content_object.content_id
            if stored_content:
                self._apply_stored_content_to_object(storage, content_object, stored_content, submission_id=submission.submission_id, text_content=text_content)
            elif storage_status in {"remote", "missing"} and content_object.storage_status != "verified":
                content_object.storage_status = storage_status
                if storage_status == "remote":
                    content_object.local_path = None
            return content_object
        content_object = self._build_content_object_for_submission(state, storage, network_name, submission, image_path, text_content, storage_status)
        if content_object is None:
            return None
        if stored_content:
            self._apply_stored_content_to_object(storage, content_object, stored_content, submission_id=submission.submission_id, text_content=text_content)
        elif storage_status == "remote":
            content_object.local_path = None
        state.content_objects.append(content_object)
        submission.content_id = content_object.content_id
        return content_object

    @staticmethod
    def _content_type_hint_for_submission(image_path="", text_content=""):
        if image_path and (text_content or "").strip(): return CONTENT_TYPE_MIXED
        return CONTENT_TYPE_IMAGE if image_path else CONTENT_TYPE_TEXT

    def register_uploaded_content(self, state, storage, network_name, *, content_hash, submitted_by, mime_type, file_size_bytes, storage_status, local_path=None, file_name=None, original_filename=None, caption=None, text_content=None, content_type_hint=None, created_at=None, byte_hash=None, hash_scheme=None):
        content_type = _validate_content_type(content_type_hint) if content_type_hint else (CONTENT_TYPE_TEXT if mime_type == TEXT_MIME_TYPE else (CONTENT_TYPE_MIXED if (text_content or "").strip() or (caption or "").strip() else CONTENT_TYPE_IMAGE))
        if mime_type == TEXT_MIME_TYPE and content_type == CONTENT_TYPE_IMAGE: content_type = CONTENT_TYPE_TEXT
        content_object = self.get_content_object_by_hash(state, storage, content_hash)
        if content_object:
            metadata = dict(content_object.metadata or {})
            if byte_hash: metadata["byte_hash"] = byte_hash
            if original_filename: metadata["original_filename"] = original_filename
            content_object.mime_type, content_object.file_size_bytes, content_object.storage_status = mime_type, file_size_bytes, storage_status
            content_object.hash_scheme = hash_scheme or content_object.hash_scheme
            if local_path: content_object.local_path = local_path
            if file_name: content_object.file_name = file_name
            if caption: content_object.caption = caption.strip()
            if text_content: content_object.text_content = text_content.strip()
            if content_object.content_type == CONTENT_TYPE_IMAGE and content_type == CONTENT_TYPE_MIXED: content_object.content_type = CONTENT_TYPE_MIXED
            content_object.metadata = metadata
            verification = verify_content_object_payload(content_object, data_dir=storage.data_dir)
            content_object.hash_scheme, content_object.verified_at, content_object.verification_error = verification["hash_scheme"], verification["verified_at"], verification["error"]
            return content_object
        content_object = ContentObject(content_hash=content_hash, content_type=content_type, mime_type=mime_type, submitted_by=submitted_by, network_name=network_name, created_at=time.time() if created_at is None else created_at, file_name=file_name, file_size_bytes=file_size_bytes, storage_status=storage_status, local_path=local_path, text_content=text_content, caption=caption, metadata={**({"byte_hash": byte_hash} if byte_hash else {}), **({"original_filename": original_filename} if original_filename else {})}, hash_scheme=hash_scheme or HASH_SCHEME_UNKNOWN, verified_at=time.time() if storage_status == "verified" else None, verification_error=None)
        verification = verify_content_object_payload(content_object, data_dir=storage.data_dir)
        content_object.hash_scheme, content_object.verified_at, content_object.verification_error = verification["hash_scheme"], verification["verified_at"], verification["error"]
        state.content_objects.append(content_object)
        return content_object

    def upload_binary_content(self, state, storage, network_name, *, file_bytes, submitted_by, mime_type, original_filename=None, caption=None, content_type_hint=None):
        payload = resolve_payload_hash(file_bytes, mime_type)
        stored = store_content_bytes(payload["content_hash"], payload["stored_bytes"], mime_type=payload["mime_type"], original_filename=sanitize_original_filename(original_filename), data_dir=storage.data_dir, hash_scheme=payload["hash_scheme"])
        return self.register_uploaded_content(state, storage, network_name, content_hash=payload["content_hash"], submitted_by=submitted_by, mime_type=stored["mime_type"], file_size_bytes=stored["file_size_bytes"], storage_status=stored["storage_status"], local_path=stored["local_path"], file_name=stored["file_name"], original_filename=stored["original_filename"], caption=validate_caption(caption), text_content=payload["text_content"], content_type_hint=content_type_hint, byte_hash=stored["byte_hash"], hash_scheme=stored["hash_scheme"])

    def upload_text_content(self, state, storage, network_name, *, text_content, submitted_by, caption=None):
        normalized = validate_text_content(text_content)
        content_hash = compute_text_content_hash(normalized)
        stored = store_content_bytes(content_hash, normalized.encode("utf-8"), mime_type=TEXT_MIME_TYPE, data_dir=storage.data_dir, hash_scheme=HASH_SCHEME_SHA256_TEXT)
        return self.register_uploaded_content(state, storage, network_name, content_hash=content_hash, submitted_by=submitted_by, mime_type=TEXT_MIME_TYPE, file_size_bytes=stored["file_size_bytes"], storage_status=stored["storage_status"], local_path=stored["local_path"], file_name=stored["file_name"], original_filename=stored["original_filename"], caption=validate_caption(caption), text_content=normalized, content_type_hint=CONTENT_TYPE_TEXT, byte_hash=stored["byte_hash"], hash_scheme=stored["hash_scheme"])

    def refresh_storage_statuses(self, state, storage):
        refreshed = False
        for content_object in state.content_objects:
            verification = verify_content_object_payload(content_object, data_dir=storage.data_dir)
            status = content_object.storage_status
            if verification["verified"]: status = "verified"
            elif verification["error"] == "missing_file" and status in {"local", "verified"}: status = "missing"
            elif verification["exists"]: status = "local"
            for field, value in (("storage_status", status), ("hash_scheme", verification["hash_scheme"]), ("verification_error", verification["error"]), ("verified_at", verification["verified_at"]), ("local_path", verification["local_path"] or content_object.local_path), ("file_size_bytes", verification["file_size_bytes"] if verification["file_size_bytes"] is not None else content_object.file_size_bytes)):
                if getattr(content_object, field) != value:
                    setattr(content_object, field, value); refreshed = True
        return refreshed

    def submit_content(self, state, storage, network_name, image_path="", text_content="", submitter=""):
        if image_path and not os.path.isfile(image_path): raise ValueError("Invalid image path provided for the submission.")
        if not image_path and not (text_content or "").strip(): raise ValueError("At least image_path or text_content is required for a submission.")
        submission = Submission(image_path=image_path or "", text_content=text_content, submitter=submitter, status=PENDING)
        stored = None
        if image_path:
            with open(image_path, "rb") as source: data = source.read()
            stored = store_content_bytes(submission.content_hash, data, mime_type=guess_mime_type(os.path.basename(image_path), "image/jpeg"), original_filename=os.path.basename(image_path), data_dir=storage.data_dir, hash_scheme=HASH_SCHEME_LEGACY)
            submission.image_path = os.path.abspath(stored["path"])
        elif (text_content or "").strip():
            stored = store_content_bytes(submission.content_hash, text_content.strip().encode("utf-8"), mime_type=TEXT_MIME_TYPE, data_dir=storage.data_dir, hash_scheme=HASH_SCHEME_LEGACY)
        state.submissions.append(submission)
        self.ensure_content_object_for_submission(state, storage, network_name, submission, submission.image_path, text_content or "", stored)
        return submission

    def link_content_objects_to_submissions(self, state, storage, network_name):
        linked = False
        for submission in state.submissions:
            content_object = self.get_content_object_by_hash(state, storage, submission.content_hash)
            if content_object:
                if submission.content_id != content_object.content_id: submission.content_id, linked = content_object.content_id, True
                resolved = resolve_local_path(content_object.local_path, data_dir=storage.data_dir)
                if resolved and content_object.content_type in {CONTENT_TYPE_IMAGE, CONTENT_TYPE_MIXED} and submission.image_path != resolved and os.path.isfile(resolved): submission.image_path, linked = resolved, True
            elif self.ensure_content_object_for_submission(state, storage, network_name, submission, submission.image_path, submission.text_content): linked = True
        return linked

    def recover_block_media_bytes(self, storage, block_or_hash, block_lookup):
        block = block_lookup(block_or_hash) if isinstance(block_or_hash, str) else block_or_hash
        if block is None: raise ValueError("Block not found.")
        media_bytes = self._block_field(block, "media_bytes")
        if media_bytes is not None: return Block.from_dict(block).media_bytes if isinstance(block, dict) else block.media_bytes
        content_hash, mime_type = self._block_field(block, "content_hash"), self._block_field(block, "mime_type")
        if not content_hash or not mime_type: raise ValueError("Block does not contain recoverable media bytes.")
        return load_content_bytes(content_hash, mime_type, data_dir=storage.data_dir)

    def resolve_protocol_v1_block_media(self, storage, block, block_lookup):
        mime_type = self._block_field(block, "mime_type")
        if not isinstance(mime_type, str) or not mime_type.strip(): raise ValueError("Protocol v1 blocks must include mime_type.")
        return resolve_declared_payload_hash(self.recover_block_media_bytes(storage, block, block_lookup), mime_type)
