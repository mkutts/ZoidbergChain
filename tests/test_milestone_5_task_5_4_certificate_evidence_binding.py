import hashlib
import sqlite3
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from blockchain import Blockchain
from originality import (
    CERTIFICATE_EVIDENCE_PROFILE,
    CHECK_UNAVAILABLE,
    CONSENSUS_IMAGEHASH_VERSION,
    CONSENSUS_OCR_IDENTITY,
    CONSENSUS_PILLOW_VERSION,
    FLAGGED_FOR_REVIEW,
    OriginalityPipeline,
    certificate_fuzzy_runtime_identity,
    originality_evidence_digest,
)
from originality_certificate import (
    OriginalityCertificate,
    build_certificate_identity_payload_v2,
    calculate_certificate_id,
    validate_certificate_for_submission,
)
from peer_sync import (
    build_originality_evidence_transfer,
    receive_peer_certificate,
    receive_peer_originality_evidence,
)
from peers import PeerStore
from protocol_v1 import (
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_json_text,
    decode_canonical_bytes,
)
from protocol_v1_originality import MILESTONE5_CERTIFICATE_VERSION
from services.canonical_reorg_service import CanonicalReorgService
from services.peer_network_errors import MalformedOriginalityEvidenceError
from storage import SQLiteStorageBackend
from submission import APPROVED, Submission, VOTE_ORIGINAL
from test_support import fund_native_wallet_with_block
from wallet import Wallet


GOLDEN_V2_CERTIFICATE_ID = "36ec6b8a5c63eb13385451b8a238550ee08464eae1e98662d3d8ce5b3341110d"
GOLDEN_V2_CANONICAL_PAYLOAD = (
    '{"approval_threshold_bps":7000,"certificate_reference_block_hash":"6666666666666666666666666666666666666666666666666666666666666666",'
    '"certificate_reference_height":8,"certificate_version":2,"content_hash":"1111111111111111111111111111111111111111111111111111111111111111",'
    '"creator_address":"0x2222222222222222222222222222222222222222","established_vote_count":null,"issued_timestamp":"1724760002.75",'
    '"minimum_established_votes":null,"minimum_valid_votes":5,"network_id":"zoidberg-public-testnet-v1","not_original_votes":1,"original_votes":4,'
    '"originality_decision":"FLAGGED_FOR_REVIEW","originality_evidence_digest":"4444444444444444444444444444444444444444444444444444444444444444",'
    '"originality_reference_block_hash":"3333333333333333333333333333333333333333333333333333333333333333","originality_reference_height":7,'
    '"originality_rule_version":1,"originality_score":"9.75","protocol_version":1,"reputation_rule_version":null,"reviewer_policy_version":null,'
    '"reviewer_snapshot_digest":null,"reviewer_snapshot_reference_block_hash":null,"reviewer_snapshot_reference_height":null,'
    '"submission_id":"submission-v2-golden","total_valid_votes":6,"unsure_votes":1,'
    '"vote_set_hash":"5555555555555555555555555555555555555555555555555555555555555555"}'
)


def _golden_fields():
    return {
        "certificate_version": 2,
        "protocol_version": 1,
        "network_id": PUBLIC_TESTNET_V1_NETWORK_ID,
        "submission_id": "submission-v2-golden",
        "content_hash": "11" * 32,
        "creator_address": "0x" + "22" * 20,
        "originality_rule_version": 1,
        "originality_decision": FLAGGED_FOR_REVIEW,
        "originality_reference_height": 7,
        "originality_reference_block_hash": "33" * 32,
        "originality_evidence_digest": "44" * 32,
        "reviewer_policy_version": None,
        "reputation_rule_version": None,
        "reviewer_snapshot_reference_height": None,
        "reviewer_snapshot_reference_block_hash": None,
        "reviewer_snapshot_digest": None,
        "minimum_valid_votes": 5,
        "minimum_established_votes": None,
        "approval_threshold_bps": 7000,
        "total_valid_votes": 6,
        "established_vote_count": None,
        "original_votes": 4,
        "not_original_votes": 1,
        "unsure_votes": 1,
        "vote_set_hash": "55" * 32,
        "certificate_reference_height": 8,
        "certificate_reference_block_hash": "66" * 32,
        "issued_timestamp": "1724760002.75",
        "originality_score": "9.75",
    }


def _issue_certificate(blockchain, submission_image, wallets, *, text="Task 5.4 evidence binding"):
    submission = blockchain.submit_content(
        image_path=str(submission_image), text_content=text,
        submitter=wallets["owner"].public_key,
    )
    for index in range(5):
        blockchain.cast_submission_vote(
            submission.submission_id, f"task-5-4-voter-{index}",
            VOTE_ORIGINAL, created_at=1_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id, automated_originality_passed=True, now=2_000
    )
    return submission, blockchain.get_originality_certificate_for_submission(
        submission.submission_id
    )


def _peer_target(source, certificate, tmp_path):
    backend = SQLiteStorageBackend(sqlite_db_path=str(tmp_path / "peer-target.db"))
    target = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    target.chain = [type(source.chain[0]).from_dict(source.chain[0].to_dict())]
    source_submission = source.get_submission(certificate.submission_id)
    target.submissions = [Submission.from_dict(source_submission.to_dict())]
    target.originality_evidence = []
    target.content_objects = []
    store = PeerStore(storage_backend=backend)
    store.register_peer("source-node", "http://source.test", "zoidberg-testnet")
    return target, store


def test_certificate_v2_has_literal_canonical_payload_and_id_golden_vector():
    fields = _golden_fields()
    payload = build_certificate_identity_payload_v2(fields)
    assert canonical_json_text(payload) == GOLDEN_V2_CANONICAL_PAYLOAD
    assert calculate_certificate_id(
        fields, certificate_version=2, network_id=PUBLIC_TESTNET_V1_NETWORK_ID
    ) == GOLDEN_V2_CERTIFICATE_ID
    assert calculate_certificate_id(
        deepcopy(fields), certificate_version=2,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    ) == GOLDEN_V2_CERTIFICATE_ID


def test_version_2_reserves_reviewer_state_as_canonical_null_and_rejects_unknown_version():
    fields = _golden_fields()
    assert build_certificate_identity_payload_v2(fields)["reviewer_policy_version"] is None
    fields["reviewer_policy_version"] = 1
    with pytest.raises(ValueError, match="reserves reviewer policy"):
        build_certificate_identity_payload_v2(fields)
    with pytest.raises(ValueError, match="Unsupported certificate_version"):
        calculate_certificate_id(_golden_fields(), certificate_version=999)


def test_new_issuance_binds_current_evidence_and_legacy_certificate_still_validates(
    blockchain, submission_image, wallets
):
    submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    evidence = blockchain.get_originality_evidence(submission.submission_id)
    assert certificate.certificate_version == MILESTONE5_CERTIFICATE_VERSION
    assert certificate.originality_rule_version == evidence["originality_rule_version"]
    assert certificate.originality_decision == evidence["final_prevote_decision"]
    assert certificate.originality_evidence_digest == evidence["canonical_evidence_digest"]
    assert certificate.originality_reference_block_hash == evidence["originality_reference_block_hash"]
    assert certificate.reviewer_policy_version is None
    assert certificate.minimum_established_votes is None
    assert blockchain.validate_originality_certificate(certificate, submission)

    legacy = OriginalityCertificate.from_approved_submission(
        submission,
        blockchain.get_submission_votes(submission.submission_id)["votes"],
        minimum_votes_required=5,
        network_name="zoidberg-testnet",
        issuing_node_id="legacy-node",
        approved_at=2_000,
        certificate_version=None,
    )
    assert legacy.certificate_version is None
    assert validate_certificate_for_submission(legacy, submission)


def test_missing_changed_or_wrong_binding_cannot_validate(
    blockchain, submission_image, wallets
):
    submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    evidence = blockchain.get_originality_evidence(submission.submission_id)
    media = blockchain._certificate_media_context(submission)
    with pytest.raises(ValueError, match="Originality evidence is required"):
        validate_certificate_for_submission(
            certificate, submission, chain=blockchain.chain, **media
        )
    changed = deepcopy(evidence)
    changed["reason_codes"] = ["TAMPERED"]
    with pytest.raises(ValueError, match="digest"):
        validate_certificate_for_submission(
            certificate, submission, originality_evidence=changed,
            chain=blockchain.chain, **media,
        )
    wrong_submission = Submission.from_dict(submission.to_dict())
    wrong_submission.submission_id = "wrong-submission"
    with pytest.raises(ValueError, match="submission_id"):
        validate_certificate_for_submission(
            certificate, wrong_submission, originality_evidence=evidence,
            chain=blockchain.chain, **media,
        )


def test_exact_duplicate_hard_reject_and_stale_binding_cannot_certify(
    blockchain, submission_image, wallets
):
    _submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    blockchain.add_to_mint_queue(certificate.submission_id)
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key, validate_meme=False
    )
    duplicate = blockchain.submit_content(
        image_path=str(submission_image), text_content="different caption",
        submitter=wallets["owner"].public_key,
    )
    with pytest.raises(ValueError, match="approved unminted|Hard rejected"):
        blockchain.create_originality_certificate(duplicate.submission_id)

    certificate.evidence_binding_status = "invalidated_by_reorg"
    original = blockchain.get_submission(certificate.submission_id)
    with pytest.raises(ValueError, match="binding is not active"):
        blockchain.validate_originality_certificate(certificate, original)


def test_peer_evidence_transfer_revalidates_media_and_is_idempotent(
    blockchain, submission_image, wallets, isolated_data_dir
):
    _submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    transfer = build_originality_evidence_transfer(blockchain, certificate)
    target, peers = _peer_target(blockchain, certificate, isolated_data_dir)
    kwargs = {
        "blockchain": target,
        "peer_store": peers,
        "origin_node_id": "source-node",
        "network_name": "zoidberg-testnet",
        "evidence_payload": transfer["evidence"],
        "media_payload": transfer["media_bytes"],
        "media_mime_type": transfer["mime_type"],
        "local_network_name": "zoidberg-testnet",
    }
    assert receive_peer_originality_evidence(**kwargs)["action"] == "created"
    assert receive_peer_originality_evidence(**kwargs)["action"] == "duplicate"
    target.originality_certificates.append(OriginalityCertificate.from_dict(certificate.to_dict()))
    assert target.originality_certificates[-1].certificate_id == certificate.certificate_id
    assert target.validate_originality_certificate(
        target.originality_certificates[-1], target.submissions[0]
    )


def test_peer_certificate_preserves_verified_text_media_for_second_validation(
    blockchain, wallets, isolated_data_dir, monkeypatch
):
    submission = blockchain.submit_content(
        image_path="",
        text_content="Task 5.4 peer text media",
        submitter=wallets["owner"].public_key,
    )
    for index in range(5):
        blockchain.cast_submission_vote(
            submission.submission_id,
            f"task-5-4-text-voter-{index}",
            VOTE_ORIGINAL,
            created_at=1_100 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=2_100,
    )
    certificate = blockchain.get_originality_certificate_for_submission(
        submission.submission_id
    )
    transfer = build_originality_evidence_transfer(blockchain, certificate)
    target, peers = _peer_target(blockchain, certificate, isolated_data_dir)

    receive_peer_originality_evidence(
        target,
        peers,
        "source-node",
        "zoidberg-testnet",
        transfer["evidence"],
        transfer["media_bytes"],
        transfer["mime_type"],
        "zoidberg-testnet",
        votes_payload=transfer["votes"],
    )
    content = target.get_content_object_by_hash(certificate.content_hash)
    content.mime_type = "text/plain"
    canonical_media = decode_canonical_bytes(transfer["media_bytes"])
    monkeypatch.setattr(
        target,
        "_certificate_media_context",
        lambda _submission: {
            "media_bytes": canonical_media,
            "mime_type": transfer["mime_type"],
        },
    )
    result = receive_peer_certificate(
        target,
        peers,
        "source-node",
        "zoidberg-testnet",
        certificate.to_dict(),
        "zoidberg-testnet",
    )

    assert result["accepted"] is True
    assert content.mime_type == "text/plain"
    assert target.validate_originality_certificate(
        target.get_originality_certificate(certificate.certificate_id),
        target.get_submission(submission.submission_id),
    )


@pytest.mark.parametrize("mutation", ["digest", "reference", "rule"])
def test_peer_evidence_rejects_tampering_and_unsupported_rules(
    blockchain, submission_image, wallets, isolated_data_dir, mutation
):
    _submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    transfer = build_originality_evidence_transfer(blockchain, certificate)
    target, peers = _peer_target(blockchain, certificate, isolated_data_dir)
    evidence = deepcopy(transfer["evidence"])
    if mutation == "digest":
        evidence["reason_codes"] = ["TAMPERED"]
    elif mutation == "reference":
        evidence["originality_reference_height"] = 99
        evidence["originality_reference_block_hash"] = "99" * 32
        evidence["canonical_evidence_digest"] = originality_evidence_digest(evidence)
    else:
        evidence["originality_rule_version"] = 999
        evidence["canonical_evidence_digest"] = originality_evidence_digest(evidence)
    with pytest.raises(MalformedOriginalityEvidenceError):
        receive_peer_originality_evidence(
            target, peers, "source-node", "zoidberg-testnet", evidence,
            transfer["media_bytes"], transfer["mime_type"], "zoidberg-testnet",
        )


def test_certificate_validation_requires_local_media(
    blockchain, submission_image, wallets, isolated_data_dir
):
    _submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    target, _peers = _peer_target(blockchain, certificate, isolated_data_dir)
    target.originality_evidence = [
        deepcopy(blockchain.get_originality_evidence(certificate.submission_id))
    ]
    target.originality_certificates = [OriginalityCertificate.from_dict(certificate.to_dict())]
    with pytest.raises(ValueError, match="media bytes are required"):
        target.validate_originality_certificate(
            target.originality_certificates[0], target.submissions[0]
        )


def test_certificate_runtime_boundary_ignores_ocr_and_local_environment(monkeypatch, tmp_path):
    runtime = certificate_fuzzy_runtime_identity()
    assert runtime == {
        "pillow_version": CONSENSUS_PILLOW_VERSION,
        "imagehash_version": CONSENSUS_IMAGEHASH_VERSION,
        "ocr_identity": CONSENSUS_OCR_IDENTITY,
    }
    payload = (Path(__file__).resolve().parents[1] / "zoidberg.jpg").read_bytes()
    submission = SimpleNamespace(
        submission_id="runtime-boundary",
        content_hash=hashlib.sha256(payload).hexdigest(),
        image_path="",
        text_content="plain deterministic text",
    )
    content = SimpleNamespace(mime_type="image/jpeg", local_path=None, text_content="plain deterministic text")
    chain = [{"index": 0, "hash": "00" * 32}]
    first = OriginalityPipeline(
        certificate_consensus=True,
        ocr=lambda _image: (_ for _ in ()).throw(AssertionError("OCR must not run")),
    ).evaluate(submission, content, chain, data_dir=str(tmp_path), media_bytes=payload, mime_type="image/jpeg")
    monkeypatch.setenv("TESSDATA_PREFIX", "C:/different/trained-data")
    monkeypatch.setenv("TESSERACT_CMD", "C:/different/tesseract.exe")
    second = OriginalityPipeline(
        certificate_consensus=True,
        ocr=lambda _image: "environment-specific OCR output",
    ).evaluate(submission, content, chain, data_dir=str(tmp_path), media_bytes=payload, mime_type="image/jpeg")
    assert first == second
    assert first["certificate_verification_profile"] == CERTIFICATE_EVIDENCE_PROFILE
    assert first["ocr_result"]["status"] == CHECK_UNAVAILABLE


def test_certificate_runtime_boundary_rejects_unpinned_image_libraries(monkeypatch):
    monkeypatch.setattr(
        "originality.package_version",
        lambda package: "0.0.0" if package == "Pillow" else CONSENSUS_IMAGEHASH_VERSION,
    )
    with pytest.raises(RuntimeError, match="runtime mismatch"):
        certificate_fuzzy_runtime_identity()


def test_reorg_invalidates_exact_certificate_revision_and_requires_new_binding(
    blockchain, submission_image, wallets
):
    fund_native_wallet_with_block(blockchain, wallets["recipient"].public_key, persist=True)
    submission, certificate = _issue_certificate(blockchain, submission_image, wallets)
    document = blockchain._serialize_blockchain_state()
    winning = [document["chain"][0], {"index": 1, "hash": "ab" * 32}]
    invalidated = CanonicalReorgService._invalidate_stale_originality_evidence(document, winning)
    stored = next(
        item for item in document["originality_certificates"]
        if item["certificate_id"] == certificate.certificate_id
    )
    assert submission.submission_id in invalidated
    assert stored["evidence_binding_status"] == "invalidated_by_reorg"
    assert document["originality_evidence"] == []
    assert next(item for item in document["submissions"] if item["submission_id"] == submission.submission_id)["certificate_id"] is None


def test_sqlite_task_53_to_54_migration_is_idempotent_and_retains_legacy_certificate(tmp_path):
    path = tmp_path / "task-5-3.db"
    backend = SQLiteStorageBackend(sqlite_db_path=str(path))
    chain = Blockchain(Wallet(), Wallet(), Wallet(), storage_backend=backend)
    submission = chain.submit_content(
        text_content="legacy certificate retained", submitter="0x" + "11" * 20
    )
    submission.status = APPROVED
    votes = [
        {"submission_id": submission.submission_id, "voter": f"legacy-{index}",
         "vote_type": VOTE_ORIGINAL, "created_at": index}
        for index in range(5)
    ]
    legacy = OriginalityCertificate.from_approved_submission(
        submission, votes, 5, "zoidberg-testnet", "legacy-node",
        approved_at=10, certificate_version=None,
    )
    chain.originality_certificates.append(legacy)
    submission.certificate_id = legacy.certificate_id
    chain.save_blockchain()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX IF EXISTS idx_certificate_evidence_submission_status")
        connection.execute("DROP TABLE IF EXISTS originality_certificate_evidence_bindings")

    SQLiteStorageBackend(sqlite_db_path=str(path))
    SQLiteStorageBackend(sqlite_db_path=str(path))
    restored = Blockchain(storage_backend=SQLiteStorageBackend(sqlite_db_path=str(path)))
    assert restored.get_originality_certificate(legacy.certificate_id).certificate_version is None
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "originality_certificate_evidence_bindings" in tables
