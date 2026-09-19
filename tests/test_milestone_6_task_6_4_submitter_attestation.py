import copy
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain import Blockchain
from content import resolve_local_path
from media_admission_policy import (
    MEDIA_ADMISSION_POLICY_ID,
    MEDIA_ADMISSION_POLICY_VERSION,
    media_admission_policy_digest,
)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_json_text
from protocol_v1_submitter_attestation import (
    ATTESTATION_DEVELOPMENT,
    ATTESTATION_LEGACY,
    ATTESTATION_REQUIRED,
    REASON_EVIDENCE_DIGEST_MISMATCH,
    REASON_INVALID_SIGNATURE,
    REASON_MEDIA_HASH_MISMATCH,
    REASON_MESSAGE_MISMATCH,
    REASON_MISSING_ATTESTATION,
    REASON_NONCE_INVALID,
    REASON_NONCE_REPLAYED,
    REASON_POLICY_MISMATCH,
    REASON_SIGNER_MISMATCH,
    REASON_SUBMISSION_MISMATCH,
    REASON_UNSUPPORTED_ATTESTATION_VERSION,
    REASON_WRONG_NETWORK,
    SUBMITTER_ATTESTATION_DOMAIN,
    SUBMITTER_ATTESTATION_STATEMENT,
    SUBMITTER_ATTESTATION_STATEMENT_ID,
    SubmitterAttestationError,
    build_submitter_attestation_message,
    build_submitter_attestation_payload,
    validate_submitter_attestation,
)
from submission import Submission
from wallet_auth import WalletAuthManager


def _signature(message, account):
    return Account.sign_message(encode_defunct(text=message), account.key).signature.hex()


def _content(blockchain, account, *, kind="text"):
    if kind == "image":
        raw = (Path(blockchain.storage.data_dir) / "zoidberg.jpg").read_bytes()
        content = blockchain.upload_binary_content_operation(
            file_bytes=raw,
            submitted_by=account.address,
            mime_type="image/jpeg",
            original_filename="zoidberg.jpg",
        )
    else:
        content = blockchain.upload_text_content_operation(
            text_content="Task 6.4 canonical text\r\nattestation",
            submitted_by=account.address,
            caption="mutable presentation caption",
        )
    return content, blockchain.technical_validation_evidence_for_content(content)


def _challenge(blockchain, account, content, evidence, *, manager=None):
    manager = manager or WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    challenge = manager.issue_submission_challenge(
        wallet_address=account.address,
        content_hash=content.content_hash,
        content_id=content.content_id,
        caption="not part of the signed identity",
        technical_validation=evidence,
    )
    return manager, challenge, _signature(challenge["message"], account)


def _record(blockchain, account, content, evidence):
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    verified = manager.verify_submission_signature(
        wallet_address=account.address,
        message=challenge["message"],
        signature=signature,
        content_hash=content.content_hash,
        content_id=content.content_id,
    )
    return challenge, verified["submitter_attestation"]


def _validate(blockchain, account, content, evidence, challenge, record, **overrides):
    raw = Path(resolve_local_path(content.local_path, data_dir=blockchain.storage.data_dir)).read_bytes()
    values = {
        "expected_wallet_address": account.address,
        "expected_submission_id": challenge["submission_id"],
        "expected_raw_media_sha256": content.content_hash,
        "expected_technical_evidence": evidence,
        "raw_media_bytes": raw,
        "expected_network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
    }
    values.update(overrides)
    return validate_submitter_attestation(record, **values)


@pytest.mark.parametrize("kind", ["image", "text"])
def test_valid_image_and_text_attestations_bind_exact_accepted_bytes(blockchain, kind):
    account = Account.create()
    content, evidence = _content(blockchain, account, kind=kind)
    challenge, record = _record(blockchain, account, content, evidence)

    assert _validate(blockchain, account, content, evidence, challenge, record) == record
    assert record["domain"] == SUBMITTER_ATTESTATION_DOMAIN
    assert record["canonical_payload"]["raw_media_sha256"] == content.content_hash
    assert record["canonical_payload"]["technical_evidence_digest"] == evidence["evidence_digest"]
    assert record["canonical_payload"]["policy_digest"] == media_admission_policy_digest()


def test_signed_attestation_persists_and_reverifies_after_restart(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    submission = blockchain.submit_signed_content_operation(
        wallet_address=account.address,
        message=challenge["message"],
        signature=signature,
        content_hash=content.content_hash,
        content_id=content.content_id,
        text_content=content.text_content,
        auth_manager=manager,
    )

    restored = Blockchain(storage_backend=blockchain.storage)
    persisted = restored.get_submission(submission.submission_id)
    assert persisted is not None
    assert persisted.attestation_requirement == ATTESTATION_REQUIRED
    assert restored.submission_attestation_status(persisted)["valid"] is True


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda record: record.update(signature="not-a-signature"), REASON_INVALID_SIGNATURE),
        (lambda record: record.update(signature="0x" + "00" * 65), REASON_INVALID_SIGNATURE),
        (lambda record: record["canonical_payload"].update(raw_media_sha256="0" * 64), REASON_MEDIA_HASH_MISMATCH),
        (lambda record: record["canonical_payload"].update(technical_evidence_digest="0" * 64), REASON_EVIDENCE_DIGEST_MISMATCH),
        (lambda record: record["canonical_payload"].update(policy_id="unknown/policy"), REASON_POLICY_MISMATCH),
        (lambda record: record["canonical_payload"].update(policy_version=999), REASON_POLICY_MISMATCH),
        (lambda record: record["canonical_payload"].update(policy_digest="0" * 64), REASON_POLICY_MISMATCH),
        (lambda record: record["canonical_payload"].update(network_id="zoidberg-mainnet-v1"), REASON_WRONG_NETWORK),
        (lambda record: record["canonical_payload"].update(submission_id="f" * 32), REASON_SUBMISSION_MISMATCH),
        (lambda record: record.update(nonce="different-nonce"), REASON_NONCE_INVALID),
        (lambda record: record.update(attestation_version=999), REASON_UNSUPPORTED_ATTESTATION_VERSION),
        (lambda record: record.pop("canonical_message_hash"), REASON_MESSAGE_MISMATCH),
    ],
)
def test_tampering_fails_with_deterministic_reason(blockchain, mutation, reason):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    challenge, original = _record(blockchain, account, content, evidence)
    record = copy.deepcopy(original)
    mutation(record)

    with pytest.raises(SubmitterAttestationError) as exc_info:
        _validate(blockchain, account, content, evidence, challenge, record)
    assert exc_info.value.reason_code == reason


def test_wrong_signer_and_altered_signature_are_rejected(blockchain):
    account = Account.create()
    attacker = Account.create()
    content, evidence = _content(blockchain, account)
    challenge, record = _record(blockchain, account, content, evidence)
    forged = copy.deepcopy(record)
    forged["signature"] = _signature(record["canonical_message"], attacker)

    with pytest.raises(SubmitterAttestationError) as exc_info:
        _validate(blockchain, account, content, evidence, challenge, forged)
    assert exc_info.value.reason_code == REASON_SIGNER_MISMATCH


def test_one_byte_media_and_canonical_text_mutations_invalidate_attestation(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    challenge, record = _record(blockchain, account, content, evidence)
    original = Path(resolve_local_path(content.local_path, data_dir=blockchain.storage.data_dir)).read_bytes()

    for mutated in (original + b"!", original.replace(b"attestation", b"Attestation")):
        with pytest.raises(SubmitterAttestationError) as exc_info:
            _validate(
                blockchain,
                account,
                content,
                evidence,
                challenge,
                record,
                raw_media_bytes=mutated,
            )
        assert exc_info.value.reason_code == REASON_EVIDENCE_DIGEST_MISMATCH


def test_stale_or_unknown_technical_evidence_is_rejected(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    challenge, record = _record(blockchain, account, content, evidence)
    stale = dict(evidence)
    stale["evidence_digest"] = "0" * 64

    with pytest.raises(SubmitterAttestationError) as exc_info:
        _validate(blockchain, account, content, stale, challenge, record)
    assert exc_info.value.reason_code == REASON_EVIDENCE_DIGEST_MISMATCH


def test_canonical_serialization_and_fixed_golden_vector():
    issued_at = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
    payload = build_submitter_attestation_payload(
        wallet_address="0x0000000000000000000000000000000000000001",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        submission_id="11" * 16,
        raw_media_sha256="22" * 32,
        policy_id=MEDIA_ADMISSION_POLICY_ID,
        policy_version=MEDIA_ADMISSION_POLICY_VERSION,
        policy_digest=media_admission_policy_digest(),
        technical_evidence_version=1,
        technical_evidence_digest="33" * 32,
        nonce="task-6.4-golden-nonce",
        issued_at=issued_at,
        expires_at=issued_at + timedelta(minutes=5),
    )
    message = build_submitter_attestation_message(**payload)
    reversed_payload = dict(reversed(list(payload.items())))

    assert build_submitter_attestation_message(**reversed_payload) == message
    assert canonical_json_text(reversed_payload) == canonical_json_text(payload)
    assert hashlib.sha256(message.encode("utf-8")).hexdigest() == (
        "f2def4f1f9640c2cdc948b76e79cb574f011467bb7a0942f73cff0aee6558615"
    )
    assert f'"statement_id":"{SUBMITTER_ATTESTATION_STATEMENT_ID}"' in message
    assert SUBMITTER_ATTESTATION_STATEMENT in message


def test_exact_replay_and_wrong_nonce_are_rejected_by_challenge_manager(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    values = {
        "wallet_address": account.address,
        "message": challenge["message"],
        "signature": signature,
        "content_hash": content.content_hash,
        "content_id": content.content_id,
    }
    manager.verify_submission_signature(**values)

    with pytest.raises(SubmitterAttestationError) as replay:
        manager.verify_submission_signature(**values)
    assert replay.value.reason_code == REASON_NONCE_REPLAYED

    altered = dict(values, message=challenge["message"].replace(challenge["nonce"], "wrong-nonce"))
    with pytest.raises(SubmitterAttestationError) as wrong_nonce:
        manager.verify_submission_signature(**altered)
    assert wrong_nonce.value.reason_code == REASON_NONCE_INVALID


def test_same_attestation_cannot_target_different_media_or_submission(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    challenge, record = _record(blockchain, account, content, evidence)

    with pytest.raises(SubmitterAttestationError) as media:
        _validate(
            blockchain,
            account,
            content,
            evidence,
            challenge,
            record,
            expected_raw_media_sha256="0" * 64,
        )
    assert media.value.reason_code == REASON_MEDIA_HASH_MISMATCH

    with pytest.raises(SubmitterAttestationError) as submission:
        _validate(
            blockchain,
            account,
            content,
            evidence,
            challenge,
            record,
            expected_submission_id="f" * 32,
        )
    assert submission.value.reason_code == REASON_SUBMISSION_MISMATCH


def test_concurrent_duplicate_submission_has_exactly_one_winner(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)

    def attempt():
        try:
            return blockchain.submit_signed_content_operation(
                wallet_address=account.address,
                message=challenge["message"],
                signature=signature,
                content_hash=content.content_hash,
                content_id=content.content_id,
                text_content=content.text_content,
                auth_manager=manager,
            )
        except SubmitterAttestationError as exc:
            return exc.reason_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _index: attempt(), range(2)))

    assert sum(isinstance(outcome, Submission) for outcome in outcomes) == 1
    assert outcomes.count(REASON_NONCE_REPLAYED) == 1


def test_durable_nonce_and_signature_replay_scan(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    submission = blockchain.submit_signed_content_operation(
        wallet_address=account.address,
        message=challenge["message"],
        signature=signature,
        content_hash=content.content_hash,
        content_id=content.content_id,
        text_content=content.text_content,
        auth_manager=manager,
    )

    with pytest.raises(SubmitterAttestationError) as exc_info:
        blockchain.ensure_submitter_attestation_not_replayed(submission.submitter_attestation)
    assert exc_info.value.reason_code == REASON_NONCE_REPLAYED


def test_missing_or_tampered_persisted_attestation_never_becomes_valid(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    submission = blockchain.submit_signed_content_operation(
        wallet_address=account.address,
        message=challenge["message"],
        signature=signature,
        content_hash=content.content_hash,
        content_id=content.content_id,
        text_content=content.text_content,
        auth_manager=manager,
    )
    submission.submitter_attestation["canonical_payload"]["policy_digest"] = "0" * 64
    blockchain.save_blockchain()

    restored = Blockchain(storage_backend=blockchain.storage)
    persisted = restored.get_submission(submission.submission_id)
    assert restored.submission_attestation_status(persisted) == {
        "status": "invalid",
        "valid": False,
        "reason_code": REASON_POLICY_MISMATCH,
    }
    persisted.submitter_attestation = None
    assert restored.submission_attestation_status(persisted)["reason_code"] == REASON_MISSING_ATTESTATION


def test_required_submission_cannot_reach_originality_review_without_attestation(blockchain):
    account = Account.create()
    content, _evidence = _content(blockchain, account)
    submission = Submission(
        image_path="",
        text_content=content.text_content,
        submitter=account.address,
        content_hash=content.content_hash,
        content_id=content.content_id,
        attestation_requirement=ATTESTATION_REQUIRED,
    )
    blockchain.submissions.append(submission)

    with pytest.raises(SubmitterAttestationError) as exc_info:
        blockchain.evaluate_prevote_originality(submission.submission_id)
    assert exc_info.value.reason_code == REASON_MISSING_ATTESTATION
    assert blockchain.get_originality_evidence(submission.submission_id) is None


def test_valid_signature_does_not_bypass_task_6_3_technical_validation(blockchain):
    account = Account.create()
    content, evidence = _content(blockchain, account)
    manager, challenge, signature = _challenge(blockchain, account, content, evidence)
    stored_path = resolve_local_path(content.local_path, data_dir=blockchain.storage.data_dir)
    with open(stored_path, "ab") as media_file:
        media_file.write(b"one-byte-mutation")

    with pytest.raises(ValueError, match="technical|evidence|hash|media",):
        blockchain.submit_signed_content_operation(
            wallet_address=account.address,
            message=challenge["message"],
            signature=signature,
            content_hash=content.content_hash,
            content_id=content.content_id,
            text_content=content.text_content,
            auth_manager=manager,
        )
    assert blockchain.get_submission(challenge["submission_id"]) is None


def test_legacy_submission_remains_readable_without_false_attestation(blockchain):
    legacy = Submission.from_dict(
        {"image_path": "", "text_content": "historical", "submitter": "legacy"}
    )
    assert legacy.attestation_requirement == ATTESTATION_LEGACY
    assert blockchain.submission_attestation_status(legacy) == {
        "status": ATTESTATION_LEGACY,
        "valid": False,
        "reason_code": None,
    }


def test_development_unsigned_record_cannot_masquerade_as_public_testnet_valid(
    blockchain, monkeypatch
):
    import blockchain as blockchain_module

    unsigned = Submission(
        image_path="",
        text_content="development only",
        submitter="developer",
        attestation_requirement=ATTESTATION_DEVELOPMENT,
    )
    monkeypatch.setattr(blockchain_module, "ENVIRONMENT", "public_testnet")

    assert blockchain.submission_attestation_status(unsigned) == {
        "status": "invalid",
        "valid": False,
        "reason_code": REASON_MISSING_ATTESTATION,
    }
