"""Feedback record transitions over caller-owned persisted collections."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass

from access_control import normalize_email, normalize_handle, normalize_text_field, utc_now_iso
from wallet_auth import normalize_wallet_address


FEEDBACK_TYPES = {"bug", "confusing_ui", "wallet_connection_issue", "mobile_issue", "access_allowlist_issue", "submission_upload_issue", "voting_review_issue", "rewards_balance_issue", "general_suggestion", "other"}
FEEDBACK_STATUSES = {"new", "reviewed", "in_progress", "resolved", "dismissed"}
ACTIVE_FEEDBACK_STATUSES = {"new", "reviewed", "in_progress"}
CLOSED_FEEDBACK_STATUSES = {"resolved", "dismissed"}
FEEDBACK_PRIORITIES = {"low", "normal", "high", "urgent"}


@dataclass
class FeedbackState:
    feedback_records: list


class FeedbackService:
    @staticmethod
    def normalize_feedback_type(feedback_type):
        value = str(feedback_type or "").strip().lower()
        if value not in FEEDBACK_TYPES:
            raise ValueError("Feedback type must be bug, confusing_ui, wallet_connection_issue, mobile_issue, access_allowlist_issue, submission_upload_issue, voting_review_issue, rewards_balance_issue, general_suggestion, or other.")
        return value

    @staticmethod
    def normalize_feedback_status(status):
        value = str(status or "").strip().lower()
        if value not in FEEDBACK_STATUSES:
            raise ValueError("Feedback status must be new, reviewed, in_progress, resolved, or dismissed.")
        return value

    @staticmethod
    def normalize_feedback_priority(priority):
        value = str(priority or "").strip().lower() or "normal"
        if value not in FEEDBACK_PRIORITIES:
            raise ValueError("Feedback priority must be low, normal, high, or urgent.")
        return value

    @staticmethod
    def normalize_feedback_dimension(value):
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            raise ValueError("Viewport dimensions must be numeric when provided.")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Viewport dimensions must be numeric when provided.") from exc
        if number < 0 or number > 20000:
            raise ValueError("Viewport dimensions must be between 0 and 20000.")
        return number

    @staticmethod
    def normalize_feedback_snapshot(value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("Feedback context snapshots must be objects when provided.")
        return json.loads(json.dumps(value))

    @staticmethod
    def get_feedback(state, feedback_id):
        candidate = str(feedback_id or "").strip()
        return next((record for record in state.feedback_records if candidate and str(record.get("feedback_id") or "").strip() == candidate), None)

    def list_feedback(self, state, *, status=None, feedback_type=None, priority=None, limit=None):
        records = list(state.feedback_records)
        if status is not None:
            status_value = str(status or "").strip().lower()
            if status_value == "active":
                records = [record for record in records if str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES]
            elif status_value == "closed":
                records = [record for record in records if str(record.get("status") or "").strip().lower() in CLOSED_FEEDBACK_STATUSES]
            elif status_value:
                records = [record for record in records if str(record.get("status") or "").strip().lower() == self.normalize_feedback_status(status_value)]
        if feedback_type is not None:
            records = [record for record in records if str(record.get("type") or "").strip().lower() == self.normalize_feedback_type(feedback_type)]
        if priority is not None:
            records = [record for record in records if str(record.get("priority") or "").strip().lower() == self.normalize_feedback_priority(priority)]
        records.sort(key=lambda record: str(record.get("updated_at") or record.get("created_at") or ""), reverse=True)
        if limit is not None:
            try:
                limit_value = max(0, int(limit))
            except (TypeError, ValueError):
                limit_value = 0
            if limit_value:
                records = records[:limit_value]
        return records

    def feedback_summary(self, state):
        records = self.list_feedback(state)
        return {"new_feedback_count": sum(str(record.get("status") or "").strip().lower() == "new" for record in records), "open_feedback_count": sum(str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES for record in records), "high_priority_feedback_count": sum(str(record.get("status") or "").strip().lower() in ACTIVE_FEEDBACK_STATUSES and str(record.get("priority") or "").strip().lower() in {"high", "urgent"} for record in records), "latest_feedback_timestamp": next((str(record.get("created_at") or "").strip() for record in records if str(record.get("created_at") or "").strip()), None)}

    def create_feedback(self, state, *, feedback_type, title, description, name=None, email=None, handle=None, wallet_address=None, access_account_id=None, current_page=None, current_flow=None, user_agent=None, remote_ip=None, browser_metadata=None, eligibility_snapshot=None, viewport_width=None, viewport_height=None, is_mobile=None, priority="normal"):
        timestamp = utc_now_iso()
        record = {"feedback_id": secrets.token_hex(16), "type": self.normalize_feedback_type(feedback_type), "title": normalize_text_field(title), "description": normalize_text_field(description), "status": "new", "priority": self.normalize_feedback_priority(priority), "name": normalize_text_field(name), "email": normalize_email(email), "handle": normalize_handle(handle), "wallet_address": normalize_wallet_address(wallet_address) if wallet_address else None, "access_account_id": normalize_text_field(access_account_id), "current_page": normalize_text_field(current_page)[:240], "current_flow": normalize_text_field(current_flow)[:128], "user_agent": normalize_text_field(user_agent)[:240], "remote_ip": normalize_text_field(remote_ip)[:120], "browser_metadata": self.normalize_feedback_snapshot(browser_metadata), "eligibility_snapshot": self.normalize_feedback_snapshot(eligibility_snapshot), "viewport_width": self.normalize_feedback_dimension(viewport_width), "viewport_height": self.normalize_feedback_dimension(viewport_height), "is_mobile": bool(is_mobile) if is_mobile is not None else None, "admin_notes": [], "created_at": timestamp, "updated_at": timestamp, "reviewed_at": None, "reviewed_by": None, "status_updated_at": timestamp, "status_updated_by": None, "resolved_at": None, "dismissed_at": None}
        if not record["title"]:
            raise ValueError("Feedback title is required.")
        if not record["description"]:
            raise ValueError("Feedback description is required.")
        state.feedback_records.append(record)
        return record

    def update_feedback(self, state, feedback_id, *, status=None, priority=None, reviewed_by="operator"):
        record = self.get_feedback(state, feedback_id)
        if record is None:
            raise ValueError(f"Feedback not found: {feedback_id}")
        timestamp = utc_now_iso()
        if status is not None:
            normalized_status = self.normalize_feedback_status(status)
            record.update(status=normalized_status, status_updated_at=timestamp, status_updated_by=normalize_text_field(reviewed_by))
            if normalized_status != "new" and not record.get("reviewed_at"):
                record.update(reviewed_at=timestamp, reviewed_by=normalize_text_field(reviewed_by))
            if normalized_status == "resolved":
                record.update(resolved_at=timestamp, dismissed_at=None)
            elif normalized_status == "dismissed":
                record.update(dismissed_at=timestamp, resolved_at=None)
            else:
                record.update(resolved_at=None, dismissed_at=None)
        if priority is not None:
            record["priority"] = self.normalize_feedback_priority(priority)
        record["updated_at"] = timestamp
        return record

    def add_feedback_admin_note(self, state, feedback_id, *, note, created_by="operator"):
        record = self.get_feedback(state, feedback_id)
        if record is None:
            raise ValueError(f"Feedback not found: {feedback_id}")
        note_text = normalize_text_field(note)
        if not note_text:
            raise ValueError("Admin note is required.")
        note_record = {"note_id": secrets.token_hex(12), "note": note_text, "created_at": utc_now_iso(), "created_by": normalize_text_field(created_by) or "operator"}
        record["admin_notes"] = list(record.get("admin_notes") or []) + [note_record]
        record["updated_at"] = note_record["created_at"]
        return note_record
