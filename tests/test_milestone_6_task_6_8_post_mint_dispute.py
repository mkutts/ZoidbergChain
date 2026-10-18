"""M6-AC16: finalized disputes add evidence without changing canonical blocks."""

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from post_mint_dispute import (DISPUTE_REASONS, dispute_identity, dispute_payload,
                               dispute_policy_digest, dispute_tally, verify_dispute)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_json_text
from tests.test_milestone_6_task_6_7_community_report import _submission


def _record(block, index, *, reason=None, status=None):
    account = Account.from_key(bytes([index]) * 32)
    payload = dispute_payload(
        wallet_address=account.address, submission_id=block.submission_id,
        block_height=block.index, block_hash=block.hash, media_hash=block.media_hash,
        reason=reason or DISPUTE_REASONS[index % len(DISPUTE_REASONS)],
        nonce=f"nonce-{index}-{reason}", issued_at="2026-10-10T00:00:00+00:00",
        expires_at="2026-10-10T00:05:00+00:00",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
    message = canonical_json_text(payload)
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return {"payload": payload, "message": message, "signature": signature,
            "identity": dispute_identity(payload, signature),
            "reviewer_reference": {"height": 0, "block_hash": "0" * 64,
                                   "status": status or ("ESTABLISHED_REVIEWER" if index == 1
                                                        else "PROBATIONARY_REVIEWER")}}


def _minted_node(isolated_data_dir, backend_name, monkeypatch):
    from blockchain import Blockchain
    from storage import JSONStorageBackend, SQLiteStorageBackend
    from tests.test_milestone_6_task_6_6_admission import _signed_votes
    from tests.test_milestone_5_task_5_9_release_readiness import _finalize
    from wallet import Wallet

    validators = [Account.create() for _ in range(3)]
    backend_type = JSONStorageBackend if backend_name == "json" else SQLiteStorageBackend
    backend = backend_type(
        blockchain_file=str(isolated_data_dir / f"dispute-{backend_name}.json"),
        peers_file=str(isolated_data_dir / f"dispute-{backend_name}-peers.json"),
        sqlite_db_path=str(isolated_data_dir / f"dispute-{backend_name}.db"))
    kwargs = {"storage_backend": backend,
              "validator_set": tuple(account.address for account in validators)}
    node = Blockchain(Wallet(), Wallet(), Wallet(), **kwargs)
    _finalize(node, validators, 0)
    submission = _submission(node)
    votes, statuses = _signed_votes(node, submission)
    # The mint certificate uses the finalized reviewer status established by
    # the existing Milestone 6 test fixture.
    monkeypatch.setattr(Blockchain, "get_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash, **kw: statuses[wallet])
    node.votes.extend(votes)
    node.evaluate_submission_operation(submission.submission_id)
    node.commit_certified_submission(submission.submission_id, validate_meme=False)
    block = node.get_protocol_v1_block_for_submission(submission.submission_id)
    _finalize(node, validators, block.index)
    return node, block, kwargs


def test_signed_dispute_domain_and_tampering():
    class Block:
        submission_id = "submission"
        index = 1
        hash = "a" * 64
        media_hash = "b" * 64
    record = _record(Block, 1)
    resolver = lambda wallet, height, block_hash: "ESTABLISHED_REVIEWER"
    args = {"submission_id": Block.submission_id, "block_height": Block.index,
            "block_hash": Block.hash, "media_hash": Block.media_hash,
            "status_resolver": resolver}
    assert verify_dispute(record, **args)
    assert record["payload"]["domain"] == "zoidbergchain/post-mint-dispute/v1"
    assert record["payload"]["policy_digest"] == dispute_policy_digest()
    for field, value in (("reason", DISPUTE_REASONS[-1]), ("submission_id", "other"),
                         ("block_height", 2), ("block_hash", "c" * 64),
                         ("media_hash", "d" * 64), ("network_id", "wrong"),
                         ("policy_version", 2), ("policy_digest", "0" * 64),
                         ("wallet_address", "0x" + "f" * 40)):
        changed = deepcopy(record)
        changed["payload"][field] = value
        assert not verify_dispute(changed, **args)
    changed = deepcopy(record)
    changed["signature"] = "0x" + "0" * 130
    assert not verify_dispute(changed, **args)
    for other_domain in ("zoidbergchain/community-report/v1",
                         "zoidbergchain/community-review/v2",
                         "zoidbergchain/submitter-attestation/v1",
                         "zoidbergchain/wallet-auth/v1"):
        changed = deepcopy(record)
        changed["message"] = canonical_json_text({**record["payload"], "domain": other_domain})
        changed["signature"] = Account.sign_message(
            encode_defunct(text=changed["message"]),
            Account.from_key(bytes([1]) * 32).key).signature.hex()
        changed["identity"] = dispute_identity(changed["payload"], changed["signature"])
        assert not verify_dispute(changed, **args)


def test_dispute_challenge_single_use_and_expiry():
    from datetime import timedelta
    from wallet_auth import WalletAuthManager

    account = Account.from_key(bytes([1]) * 32)
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    kwargs = {"wallet_address": account.address, "submission_id": "submission",
              "block_height": 1, "block_hash": "a" * 64, "media_hash": "b" * 64,
              "reason": DISPUTE_REASONS[0]}
    challenge = manager.issue_dispute_challenge(**kwargs)
    signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
    assert manager.verify_dispute_challenge(wallet_address=account.address,
                                            message=challenge["message"], signature=signature) == challenge["payload"]
    with pytest.raises(ValueError, match="already been used"):
        manager.verify_dispute_challenge(wallet_address=account.address,
                                         message=challenge["message"], signature=signature)
    expired = manager.issue_dispute_challenge(**kwargs)
    from wallet_auth import hash_wallet_message
    manager._dispute_challenges_by_message_hash[hash_wallet_message(expired["message"])]["expires_at"] -= timedelta(hours=1)
    with pytest.raises(ValueError, match="expired"):
        manager.verify_dispute_challenge(wallet_address=account.address,
                                         message=expired["message"],
                                         signature=Account.sign_message(encode_defunct(text=expired["message"]),
                                                                        account.key).signature.hex())


def test_dispute_tally_order_and_one_wallet_weight():
    class Block:
        submission_id = "submission"
        index = 1
        hash = "a" * 64
        media_hash = "b" * 64
    records = [_record(Block, i) for i in (1, 2, 3)]
    args = {"submission_id": Block.submission_id, "block_height": Block.index,
            "block_hash": Block.hash, "media_hash": Block.media_hash}
    assert not dispute_tally(records[:1], **args)["threshold_met"]
    assert not dispute_tally(records[:2], **args)["threshold_met"]
    expected = dispute_tally(records, **args)
    assert expected == dispute_tally(list(reversed(records)), **args)
    assert expected["threshold_met"] and expected["counted_dispute_count"] == 3
    assert expected["established_disputer_count"] == 1
    assert sum(expected["reason_counts"].values()) == 3
    probation = [_record(Block, i, status="PROBATIONARY_REVIEWER") for i in (1, 2, 3)]
    assert not dispute_tally(probation, **args)["threshold_met"]
    conflict = _record(Block, 1, reason=DISPUTE_REASONS[-1])
    one = dispute_tally(records + [conflict], **args)
    two = dispute_tally([conflict] + list(reversed(records)), **args)
    assert one == two and one["counted_dispute_count"] == 3
    selected = next(item for item in one["dispute_set"]
                    if item["wallet_address"] == records[0]["payload"]["wallet_address"])
    assert selected["identity"] == min(records[0]["identity"], conflict["identity"])


@pytest.mark.parametrize("backend_name", ["json", "sqlite"])
def test_finalized_dispute_immutable_restart_and_conflict(isolated_data_dir, monkeypatch, backend_name):
    node, block, kwargs = _minted_node(isolated_data_dir, backend_name, monkeypatch)
    records = [_record(block, i) for i in (1, 2, 3)]
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in records}
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    stale_facade = type(node)(**kwargs)
    before = deepcopy(block.to_dict())
    finality = deepcopy(node.finalized_blocks)
    tip = node.chain[-1].hash
    certificate = deepcopy(block.admission_certificate)
    assert node.dispute_status(block.submission_id)["counted_dispute_count"] == 0
    for index, record in enumerate(records):
        result = node.record_post_mint_dispute_operation(record)
        assert result["action"] == "accepted"
        assert result["status"]["threshold_met"] == (index == 2)
    assert node.record_post_mint_dispute_operation(records[0])["action"] == "duplicate"
    conflict = _record(block, 1, reason=DISPUTE_REASONS[-1])
    assert node.record_post_mint_dispute_operation(conflict)["action"] == "conflict_recorded"
    status = node.dispute_status(block.submission_id)
    assert status["counted_dispute_count"] == 3 and status["threshold_met"]
    assert node.chain[-1].hash == tip
    assert block.to_dict() == before
    assert block.admission_certificate == certificate
    assert node.finalized_blocks == finality
    stale_facade.save_blockchain()
    restarted = type(node)(**kwargs)
    assert restarted.dispute_status(block.submission_id) == status
    assert restarted.chain[-1].to_dict() == before
    assert restarted.finalized_blocks == finality
    with pytest.raises(ValueError, match="Post-mint dispute flow required"):
        node.record_community_report_operation({"payload": {"submission_id": block.submission_id},
                                                "message": "", "signature": "0x" + "0" * 130,
                                                "identity": "", "reviewer_reference": {"height": 0,
                                                "block_hash": "0" * 64, "status": "ESTABLISHED_REVIEWER"}})


def test_unfinalized_media_rejected(isolated_data_dir, monkeypatch):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    def remove_finality(document):
        document["finalized_blocks"] = [item for item in document["finalized_blocks"]
                                         if item["block_height"] != block.index]
        return document
    node.storage.atomic_update_blockchain_document(remove_finality)
    with pytest.raises(ValueError, match="not finalized"):
        node.record_post_mint_dispute_operation(_record(block, 1))


def test_dispute_api_challenge_status_and_retry(isolated_data_dir, monkeypatch):
    from tests.api.test_wallet_auth_api import _client, _verified_headers

    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    account = Account.from_key(bytes([1]) * 32)
    monkeypatch.setattr(type(node), "get_report_reviewer_decision", lambda self, wallet: {
        "status": "ESTABLISHED_REVIEWER", "reference_finalized_height": 0,
        "reference_finalized_block_hash": node.chain[0].hash})
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    client, _ = _client(node)
    headers = _verified_headers(client, account)
    policy = client.get("/disputes/policy")
    assert policy.status_code == 200
    assert policy.json()["policy_digest"] == dispute_policy_digest()
    status = client.get(f"/submissions/{block.submission_id}/disputes/status")
    assert status.status_code == 200 and status.json()["finalized"]
    challenge = client.post(f"/submissions/{block.submission_id}/disputes/challenge",
        json={"wallet_address": account.address, "submission_id": block.submission_id,
              "reason": DISPUTE_REASONS[0]}, headers=headers)
    assert challenge.status_code == 200, challenge.text
    message = challenge.json()["message"]
    assert challenge.json()["payload"]["block_hash"] == block.hash
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    request = {"wallet_address": account.address, "message": message, "signature": signature}
    accepted = client.post(f"/submissions/{block.submission_id}/disputes", json=request,
                           headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"]["counted_dispute_count"] == 1
    retry = client.post(f"/submissions/{block.submission_id}/disputes", json=request,
                        headers=headers)
    assert retry.status_code == 200 and retry.json()["action"] == "duplicate"
    invalid = client.post(f"/submissions/{block.submission_id}/disputes",
        json={**request, "signature": "0x" + "0" * 130}, headers=headers)
    assert invalid.status_code == 400
    assert node.chain[block.index].hash == block.hash


def test_cross_node_reversed_observations_converge(isolated_data_dir, monkeypatch):
    from blockchain import Blockchain
    from storage import JSONStorageBackend

    first, block, kwargs = _minted_node(isolated_data_dir, "json", monkeypatch)
    second_backend = JSONStorageBackend(
        blockchain_file=str(isolated_data_dir / "dispute-peer.json"),
        peers_file=str(isolated_data_dir / "dispute-peer-peers.json"))
    second_backend.save_blockchain_document(deepcopy(first.storage.load_blockchain_document()))
    second = Blockchain(storage_backend=second_backend, validator_set=kwargs["validator_set"])
    records = [_record(block, i) for i in (1, 2, 3)]
    conflict = _record(block, 1, reason=DISPUTE_REASONS[-1])
    statuses = {item["payload"]["wallet_address"]: item["reviewer_reference"]["status"]
                for item in records}
    monkeypatch.setattr(Blockchain, "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for item in records + [conflict]:
        first.record_post_mint_dispute_operation(item)
    for item in ([conflict] + list(reversed(records)))[:-1]:
        second.record_post_mint_dispute_operation(item)
    assert second.dispute_status(block.submission_id)["observed_dispute_count"] == 3
    assert first.dispute_status(block.submission_id)["observed_dispute_digest"] != \
        second.dispute_status(block.submission_id)["observed_dispute_digest"]
    for item in first.post_mint_disputes[block.submission_id]:
        second.record_post_mint_dispute_operation(item)
    assert first.dispute_status(block.submission_id) == second.dispute_status(block.submission_id)
    assert first.post_mint_disputes == second.post_mint_disputes
    assert first.chain[-1].to_dict() == second.chain[-1].to_dict()
    invalid = deepcopy(records[0])
    invalid["payload"]["policy_version"] = 2
    with pytest.raises(ValueError, match="Invalid signed dispute"):
        second.record_post_mint_dispute_operation(invalid)
    wrong_block = deepcopy(records[0])
    wrong_block["payload"]["block_hash"] = "a" * 64
    with pytest.raises(ValueError, match="exact finalized media block"):
        second.record_post_mint_dispute_operation(wrong_block)


def test_indexed_eligibility_avoids_ancestry_on_thousand_blocks(blockchain, monkeypatch):
    from types import SimpleNamespace
    from services.report_reviewer_index import qualification_snapshot, reference_key
    from services.reviewer_eligibility_service import ReviewerEligibilityService

    account = Account.from_key(bytes([1]) * 32)
    blocks = [SimpleNamespace(index=height, hash=f"{height:064x}",
                              creator_wallet=account.address if height < 4 else None,
                              submission_id=f"earned-{height}" if height < 4 else None,
                              native_transactions=[]) for height in range(1000)]
    snapshot = qualification_snapshot(blocks, 999, f"{999:064x}")
    blockchain.chain = blocks
    blockchain.finalized_blocks = [{"block_height": 999, "block_hash": f"{999:064x}"}]
    blockchain._report_reviewer_index = {reference_key(999, f"{999:064x}"): snapshot}
    def forbidden(*args, **kwargs):
        raise AssertionError("Whole-chain ancestry traversal in dispute verification")
    monkeypatch.setattr(ReviewerEligibilityService, "finalized_context", forbidden)
    class Media:
        submission_id = "media"
        index = 999
        hash = f"{999:064x}"
        media_hash = "b" * 64
    record = _record(Media, 1, status="PROBATIONARY_REVIEWER")
    record["reviewer_reference"] = {"height": 999, "block_hash": f"{999:064x}",
                                    "status": "PROBATIONARY_REVIEWER"}
    assert verify_dispute(record, submission_id=Media.submission_id,
                          block_height=Media.index, block_hash=Media.hash,
                          media_hash=Media.media_hash,
                          status_resolver=blockchain.get_report_reviewer_status_at_reference)


def test_dispute_rebroadcast_requires_verified_wallet(isolated_data_dir, monkeypatch):
    from tests.api.test_wallet_auth_api import _client, _verified_headers

    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    account = Account.from_key(bytes([1]) * 32)
    record = _record(block, 1)
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    node.record_post_mint_dispute_operation(record)
    client, _ = _client(node)
    path = f"/submissions/{block.submission_id}/disputes/broadcast"
    assert client.post(path).status_code == 401
    headers = _verified_headers(client, account)
    response = client.post(path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["dispute_count"] == 1


def test_peer_receive_independently_validates_signed_dispute(isolated_data_dir, monkeypatch):
    from tests.api.test_peer_vote_sync_api import _client, _register_peer

    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    record = _record(block, 1)
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    client = _client(node)
    _register_peer()
    body = {"origin_node_id": "peer-node-1", "network_name": "zoidberg-testnet",
            "dispute": record}
    received = client.post("/peers/disputes/receive", json=body)
    assert received.status_code == 200, received.text
    assert received.json()["status"]["counted_dispute_count"] == 1
    assert client.post("/peers/disputes/receive", json=body).json()["action"] == "duplicate"
    invalid = deepcopy(record)
    invalid["payload"]["reason"] = DISPUTE_REASONS[-1]
    assert client.post("/peers/disputes/receive", json={**body, "dispute": invalid}).status_code == 400


def test_concurrent_retry_counts_once_and_creator_cannot_dispute(isolated_data_dir, monkeypatch):
    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    record = _record(block, 1)
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(node.record_post_mint_dispute_operation, [record, record]))
    assert sorted(item["action"] for item in outcomes) == ["accepted", "duplicate"]
    assert node.dispute_status(block.submission_id)["counted_dispute_count"] == 1
    creator = Account.from_key(bytes.fromhex("aa" * 32))
    payload = dispute_payload(
        wallet_address=creator.address, submission_id=block.submission_id,
        block_height=block.index, block_hash=block.hash, media_hash=block.media_hash,
        reason=DISPUTE_REASONS[0], nonce="self", issued_at="2026-10-10T00:00:00+00:00",
        expires_at="2026-10-10T00:05:00+00:00")
    message = canonical_json_text(payload)
    signature = Account.sign_message(encode_defunct(text=message), creator.key).signature.hex()
    self_record = {"payload": payload, "message": message, "signature": signature,
                   "identity": dispute_identity(payload, signature),
                   "reviewer_reference": {"height": 0, "block_hash": node.chain[0].hash,
                                          "status": "ESTABLISHED_REVIEWER"}}
    with pytest.raises(ValueError, match="creator cannot dispute"):
        node.record_post_mint_dispute_operation(self_record)


def test_dispute_evidence_survives_migration_and_portable_export(isolated_data_dir, monkeypatch):
    from storage import JSONStorageBackend, SQLiteStorageBackend
    from storage_migration import migrate_json_to_sqlite
    from storage_tools import export_storage, import_storage

    node, block, _ = _minted_node(isolated_data_dir, "json", monkeypatch)
    monkeypatch.setattr(type(node), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    node.record_post_mint_dispute_operation(_record(block, 1))
    expected = node.storage.load_blockchain_state()["post_mint_disputes"]
    target_db = isolated_data_dir / "dispute-migrated.db"
    migrate_json_to_sqlite(node.storage.blockchain_file, target_db)
    sqlite_backend = SQLiteStorageBackend(sqlite_db_path=str(target_db))
    assert sqlite_backend.load_blockchain_state()["post_mint_disputes"] == expected
    export_path = isolated_data_dir / "dispute-export.json"
    export_storage(node.storage, output_path=export_path)
    portable_backend = JSONStorageBackend(
        blockchain_file=str(isolated_data_dir / "dispute-imported.json"),
        peers_file=str(isolated_data_dir / "dispute-imported-peers.json"))
    import_storage(portable_backend, input_path=export_path)
    assert portable_backend.load_blockchain_state()["post_mint_disputes"] == expected
    assert portable_backend.load_chain() == node.storage.load_chain()


def test_dispute_reviewer_vote_lookup_is_wallet_indexed(isolated_data_dir):
    from storage import SQLiteStorageBackend
    from services.reviewer_eligibility_service import ReviewerEligibilityService
    from tests.test_milestone_5_task_5_5_earned_reviewer_eligibility import _vote

    backend = SQLiteStorageBackend(sqlite_db_path=str(isolated_data_dir / "dispute-votes.db"))
    reviewer = Account.from_key(bytes([1]) * 32).address
    unrelated = Account.from_key(bytes([2]) * 32).address
    _vote(backend, reviewer, 1, height=20)
    _vote(backend, unrelated, 2, height=20)
    assert len(backend.list_durable_votes()) == 2
    assert len(backend.list_durable_votes_for_reviewer(reviewer)) == 1
    assert len(ReviewerEligibilityService._accepted_votes(backend, reviewer.lower())) == 1
    with backend._connect() as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT evidence_id FROM durable_vote_records WHERE voter_address = ?",
            (reviewer.lower(),)).fetchall()
    assert any("reviewer_durable_votes_lookup" in str(row) for row in plan)
