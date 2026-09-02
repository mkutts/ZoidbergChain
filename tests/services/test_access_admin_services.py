from services.access_admin_service import AccessAdminService, AccessAdminState
from services.feedback_service import FeedbackService, FeedbackState
from storage import JSONStorageBackend, SQLiteStorageBackend


WALLET_ONE = "0x1111111111111111111111111111111111111111"
WALLET_TWO = "0x2222222222222222222222222222222222222222"


def test_allowlist_normalization_matching_and_lifecycle():
    state = AccessAdminState([], [], [], [], [], [])
    service = AccessAdminService()
    entry = service.create_allowlist_entry(
        state,
        scope=" REVIEW ",
        subject_type="wallet",
        subject_value=WALLET_ONE.upper(),
        reason=" early tester ",
    )

    assert entry["scope"] == "review"
    assert entry["subject_value"] == WALLET_ONE
    assert service.find_matching_allowlist_entry(state, "voting", wallet_address=WALLET_ONE) is entry
    service.revoke_allowlist_entry(state, entry["allowlist_entry_id"], revoked_reason="hold")
    assert service.find_matching_allowlist_entry(state, "voting", wallet_address=WALLET_ONE) is None
    service.reactivate_allowlist_entry(state, entry["allowlist_entry_id"], reason="again")
    assert entry["status"] == "active"
    assert entry["revoked_at"] is None
    assert entry["revoked_reason"] == ""


def test_access_request_invite_login_and_wallet_binding_transitions():
    state = AccessAdminState([], [], [], [], [], [])
    service = AccessAdminService()
    request = service.create_access_request(state, name=" Tester ", email="TEST@example.test")
    account, invite_code = service.approve_access_request(state, request["request_id"], reviewed_by="qa")

    assert service.resolve_access_account_by_invite_code(state, invite_code) is account
    assert service.mark_access_account_login(state, account["access_account_id"])["last_login_at"]
    binding = service.bind_wallet_to_access_account(state, account["access_account_id"], WALLET_ONE)
    assert binding["status"] == "active"
    assert account["invite_code_hash"] is None
    assert service.bind_wallet_to_access_account(state, account["access_account_id"], WALLET_ONE) is binding
    try:
        service.bind_wallet_to_access_account(state, account["access_account_id"], WALLET_TWO)
    except ValueError as exc:
        assert str(exc) == "Access account has reached the maximum number of bound wallets."
    else:
        raise AssertionError("wallet limit was not enforced")
    service.revoke_wallet_binding(state, WALLET_ONE)
    assert account["bound_wallets"] == []


def test_access_rejection_override_and_audit_sorting():
    state = AccessAdminState([], [], [], [], [], [])
    service = AccessAdminService()
    request = service.create_access_request(state, name="Tester", email="reject@example.test")
    assert service.reject_access_request(state, request["request_id"])["status"] == "rejected"
    override = service.create_override_request(state, requested_scope="access", email="tester@example.test")
    assert service.update_override_request_status(
        state, override["override_request_id"], status="approved", resolved_scope="review"
    )["resolved_scope"] == "review"
    older = service.append_audit_log_entry(state, {"action": "event", "timestamp": "2025-01-01T00:00:00+00:00"})
    newer = service.append_audit_log_entry(state, {"action": "event", "timestamp": "2025-01-02T00:00:00+00:00"})
    assert service.list_audit_log_entries(state, action="EVENT", limit=1) == [newer]
    assert older["result"] == "ok"


def test_feedback_create_filter_update_and_notes():
    state = FeedbackState([])
    service = FeedbackService()
    record = service.create_feedback(
        state,
        feedback_type="BUG",
        title="Bug",
        description="Description",
        browser_metadata={"platform": "test"},
        viewport_width="1200",
    )
    service.update_feedback(state, record["feedback_id"], status="resolved", priority="urgent", reviewed_by="qa")
    note = service.add_feedback_admin_note(state, record["feedback_id"], note="fixed", created_by="qa")

    assert record["type"] == "bug"
    assert record["status"] == "resolved"
    assert record["priority"] == "urgent"
    assert service.list_feedback(state, status="active") == []
    assert service.list_feedback(state, status="closed") == [record]
    assert record["admin_notes"] == [note]
    assert service.feedback_summary(state)["open_feedback_count"] == 0


def test_service_records_round_trip_through_json_and_sqlite_storage(tmp_path):
    access_state = AccessAdminState([], [], [], [], [], [])
    feedback_state = FeedbackState([])
    allowlist = AccessAdminService().create_allowlist_entry(
        access_state, scope="access", subject_type="wallet", subject_value=WALLET_ONE
    )
    feedback = FeedbackService().create_feedback(
        feedback_state, feedback_type="bug", title="Stored", description="Round trip"
    )
    state = {"allowlist_entries": access_state.allowlist_entries, "feedback_records": feedback_state.feedback_records}
    backends = [
        JSONStorageBackend(blockchain_file=str(tmp_path / "state.json"), peers_file=str(tmp_path / "peers.json")),
        SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "state.db"), peers_file=str(tmp_path / "sqlite-peers.json")),
    ]

    for backend in backends:
        backend.save_blockchain_state(state)
        restored = backend.load_blockchain_state()
        assert restored["allowlist_entries"] == [allowlist]
        assert restored["feedback_records"] == [feedback]
