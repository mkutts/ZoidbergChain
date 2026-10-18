"""Milestone 6 Task 6.11 adversarial release-readiness coverage.

These tests intentionally cross protocol boundaries.  They supplement the
focused Task 6.3--6.10 suites rather than replacing their detailed vectors.
"""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from admission_certificate import validate_admission_certificate
from block import Block
from community_report import REPORT_REASONS, report_tally, verify_report
from content import load_content_bytes
from media_integrity import MediaIntegrityError, verify_media_block
from post_mint_dispute import DISPUTE_REASONS, dispute_tally, verify_dispute
from protocol_v1 import canonical_hash
from submission import QUARANTINED, QUEUED
from tests.blockchain.test_protocol_v1_block_format import _mint_protocol_v1_block
from tests.test_milestone_6_task_6_6_admission import _current_submission, _signed_votes
from tests.test_milestone_6_task_6_7_community_report import _report, _submission
from tests.test_milestone_6_task_6_8_post_mint_dispute import _minted_node, _record


def _certificate(chain):
    submission, content, _evidence = _current_submission(chain)
    votes, statuses = _signed_votes(chain, submission)
    resolver = lambda wallet, height, block_hash: statuses[wallet]
    chain.get_reviewer_status_at_reference = resolver
    chain.votes.extend(votes)
    chain.evaluate_submission_operation(submission.submission_id)
    media = load_content_bytes(
        content.content_hash, content.mime_type, data_dir=chain.storage.data_dir
    )
    return submission, deepcopy(submission.admission_certificate), resolver, media


def _rehash_certificate(certificate):
    body = {key: value for key, value in certificate.items()
            if key != "certificate_digest"}
    certificate["certificate_digest"] = canonical_hash(body)
    return certificate


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("network_id", "wrong-network"),
        lambda value: value.__setitem__("submission_id", "cross-submission-replay"),
        lambda value: value.__setitem__("policy_digest", "0" * 64),
        lambda value: value["technical_evidence"].__setitem__("raw_media_sha256", "0" * 64),
        lambda value: value["attestation"].__setitem__("nonce", "replayed-nonce"),
        lambda value: value["votes"][0].__setitem__("vote_type", "not_original"),
        lambda value: value["votes"][0].__setitem__(
            "dimension",
            "originality"
            if value["votes"][0]["dimension"] == "admissibility"
            else "admissibility",
        ),
    ],
)
def test_certificate_rejects_cross_domain_replay_and_tampered_evidence(
    blockchain, mutation
):
    _submission_record, certificate, resolver, media = _certificate(blockchain)
    mutation(certificate)
    _rehash_certificate(certificate)
    with pytest.raises(ValueError):
        validate_admission_certificate(
            certificate, media_bytes=media, reviewer_status_resolver=resolver
        )


def test_one_bit_media_change_and_block_certificate_swaps_fail(blockchain):
    submission, certificate, resolver, original = _certificate(blockchain)
    changed = bytearray(original)
    changed[0] ^= 1
    with pytest.raises(ValueError):
        validate_admission_certificate(
            certificate, media_bytes=bytes(changed), reviewer_status_resolver=resolver
        )

    assert blockchain.commit_certified_submission(
        submission.submission_id, validate_meme=False
    )
    record = blockchain.chain[-1].to_dict()
    record["media_bytes"]["$value"] = (
        ("0" if record["media_bytes"]["$value"][0] != "0" else "1")
        + record["media_bytes"]["$value"][1:]
    )
    record["hash"] = Block.calculate_hash_v1_from_dict(record)
    with pytest.raises(MediaIntegrityError):
        verify_media_block(record)


def test_stale_or_forged_current_queue_entry_is_quarantined(blockchain):
    submission, _content, _evidence = _current_submission(blockchain)
    submission.status = QUEUED
    submission.admission_certificate = None
    submission.certificate_id = "0" * 64
    blockchain.mint_queue.append(submission.submission_id)

    assert blockchain.remove_invalid_mint_queue_entries() == [submission.submission_id]
    assert submission.status == QUARANTINED
    assert submission.quarantine_reason == "invalid_admission_queue_entry"
    assert submission.submission_id not in blockchain.mint_queue
    with pytest.raises(ValueError):
        blockchain.commit_certified_submission(
            submission.submission_id, validate_meme=False
        )


def test_activation_boundary_rejects_legacy_downgrade_and_unknown_version(
    blockchain, submission_image, wallets
):
    _submission_record, _certificate_record, legacy = _mint_protocol_v1_block(
        blockchain, submission_image, wallets
    )
    activation = blockchain.configure_admission_activation()["activation_height"]
    assert activation == legacy.index + 1

    for version in (1, 999):
        forged = legacy.to_dict()
        forged["index"] = activation
        forged["previous_hash"] = legacy.hash
        forged["block_version"] = version
        forged["hash"] = blockchain.calculate_hash_from_dict(forged)
        with pytest.raises(ValueError):
            blockchain._block_validation_service.validate_block(
                forged,
                blockchain._block_validation_collaborators(),
                prior_chain=blockchain.get_chain(),
            )


def test_report_and_dispute_conflicts_converge_in_any_delivery_order():
    submission = SimpleNamespace(submission_id="task-611", content_hash="a" * 64)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    reports.append(_report(submission, 1, reason=REPORT_REASONS[-1]))
    report_args = {
        "submission_id": submission.submission_id,
        "content_hash": submission.content_hash,
    }
    first_report = report_tally(reports, **report_args)
    second_report = report_tally(list(reversed(reports)), **report_args)
    assert first_report == second_report
    assert first_report["threshold_met"]
    assert first_report["accepted_report_count"] == 3

    block = SimpleNamespace(
        submission_id=submission.submission_id,
        index=1,
        hash="b" * 64,
        media_hash=submission.content_hash,
    )
    disputes = [_record(block, index) for index in (1, 2, 3)]
    disputes.append(_record(block, 1, reason=DISPUTE_REASONS[-1]))
    dispute_args = {
        "submission_id": block.submission_id,
        "block_height": block.index,
        "block_hash": block.hash,
        "media_hash": block.media_hash,
    }
    first_dispute = dispute_tally(disputes, **dispute_args)
    second_dispute = dispute_tally(list(reversed(disputes)), **dispute_args)
    assert first_dispute == second_dispute
    assert first_dispute["threshold_met"]
    assert first_dispute["counted_dispute_count"] == 3


def test_report_and_dispute_signatures_cannot_cross_domains():
    submission = SimpleNamespace(submission_id="task-611", content_hash="a" * 64)
    report = _report(submission, 1)
    block = SimpleNamespace(
        submission_id=submission.submission_id,
        index=1,
        hash="b" * 64,
        media_hash=submission.content_hash,
    )
    dispute = _record(block, 1)
    resolver = lambda wallet, height, block_hash: "ESTABLISHED_REVIEWER"

    crossed_report = deepcopy(report)
    crossed_report["message"] = dispute["message"]
    crossed_report["signature"] = dispute["signature"]
    assert not verify_report(
        crossed_report,
        submission_id=submission.submission_id,
        content_hash=submission.content_hash,
        status_resolver=resolver,
    )

    crossed_dispute = deepcopy(dispute)
    crossed_dispute["message"] = report["message"]
    crossed_dispute["signature"] = report["signature"]
    assert not verify_dispute(
        crossed_dispute,
        submission_id=block.submission_id,
        block_height=block.index,
        block_hash=block.hash,
        media_hash=block.media_hash,
        status_resolver=resolver,
    )


def test_report_quarantine_survives_stale_facade_save(blockchain, monkeypatch):
    submission = _submission(blockchain)
    stale = type(blockchain)(storage_backend=blockchain.storage)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    statuses = {
        record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
        for record in reports
    }
    monkeypatch.setattr(
        type(blockchain),
        "get_report_reviewer_status_at_reference",
        lambda self, wallet, height, block_hash: statuses[wallet],
    )
    for record in reports:
        blockchain.record_community_report_operation(record)
    with pytest.raises(ValueError, match="Stale community reporting state"):
        stale.save_blockchain()

    restarted = type(blockchain)(storage_backend=blockchain.storage)
    restored = restarted.get_submission(submission.submission_id)
    assert restored.status == QUARANTINED
    assert restored.quarantine_reason == "community_report_threshold"
    assert restarted.report_status(submission.submission_id)["threshold_met"]


def test_peer_reproduction_preserves_block_hash_certificate_and_exact_media(
    isolated_data_dir, monkeypatch
):
    from blockchain import Blockchain
    from peer_sync import receive_peer_block
    from peers import PeerStore
    from storage import JSONStorageBackend

    source, block, kwargs = _minted_node(isolated_data_dir, "json", monkeypatch)
    peer_dir = isolated_data_dir / "task-611-independent-peer"
    peer_dir.mkdir()
    backend = JSONStorageBackend(
        blockchain_file=str(peer_dir / "blockchain.json"),
        peers_file=str(peer_dir / "peers.json"),
    )
    peer = Blockchain(storage_backend=backend, validator_set=kwargs["validator_set"])
    store = PeerStore(storage_backend=backend)
    store.register_peer(
        node_id="source",
        url="http://source.test:8000",
        network_name="zoidberg-testnet",
    )
    result = receive_peer_block(
        peer,
        store,
        "source",
        "zoidberg-testnet",
        deepcopy(block.to_dict()),
        block.submission_id,
        "zoidberg-testnet",
    )
    assert result["accepted"] is True
    accepted = peer.chain[-1]
    assert accepted.hash == source.chain[-1].hash
    assert accepted.admission_certificate["certificate_digest"] == block.certificate_id
    assert accepted.media_hash == block.media_hash
    assert bytes(accepted.media_bytes) == bytes(block.media_bytes)


def test_privileged_routes_reject_unauthorized_requests_and_no_force_route_exists(
    blockchain
):
    from tests.api.test_wallet_auth_api import _client

    submission = _submission(blockchain)
    client, _manager = _client(blockchain)
    wallet = "0x" + "1" * 40
    challenge = client.post(
        f"/submissions/{submission.submission_id}/reports/challenge",
        json={
            "wallet_address": wallet,
            "submission_id": submission.submission_id,
            "reason": REPORT_REASONS[0],
        },
    )
    assert challenge.status_code in {401, 403}
    peer_receive = client.post(
        "/peers/reports/receive",
        json={
            "origin_node_id": "untrusted-peer",
            "network_name": "zoidberg-testnet",
            "report": {},
        },
    )
    assert peer_receive.status_code >= 400

    paths = {route.path for route in client.app.routes}
    forbidden_fragments = {
        "force-admit",
        "force-mint",
        "force-unquarantine",
        "clear-dispute",
        "delete-finalized-media",
        "finality-override",
        "activation/mutate",
    }
    assert not any(fragment in path for fragment in forbidden_fragments for path in paths)


def test_forged_lifecycle_state_never_becomes_mintable(blockchain):
    from tests.api.test_wallet_auth_api import _client

    submission = _submission(blockchain)
    submission.status = "approved"
    submission.admission_state = "admitted"
    submission.admission_certificate = None
    submission.certificate_id = "0" * 64
    client, _manager = _client(blockchain)

    response = client.get(
        f"/submissions/{submission.submission_id}/lifecycle",
        params={"verify_integrity": "false"},
    )
    assert response.status_code == 200
    lifecycle = response.json()["lifecycle"]
    assert lifecycle["stage"] != "mintable"
    assert lifecycle["admission"]["qualified"] is False
    assert lifecycle["mint"]["eligible"] is False
