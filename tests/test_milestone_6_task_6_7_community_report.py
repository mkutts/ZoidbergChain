from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from community_report import (REPORT_REASONS, report_identity, report_message,
                              report_payload, report_policy_digest, report_tally,
                              verify_report)
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from wallet_auth import WalletAuthManager


def _sign(message, account):
    return Account.sign_message(encode_defunct(text=message), account.key).signature.hex()


def _submission(chain):
    creator = Account.from_key(bytes.fromhex("aa" * 32))
    content = chain.upload_text_content_operation(
        text_content="Reportable current media", submitted_by=creator.address)
    evidence = chain.technical_validation_evidence_for_content(content)
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    challenge = manager.issue_submission_challenge(
        wallet_address=creator.address, content_hash=content.content_hash,
        content_id=content.content_id, caption="", technical_validation=evidence)
    return chain.submit_signed_content_operation(
        wallet_address=creator.address, message=challenge["message"],
        signature=_sign(challenge["message"], creator), content_hash=content.content_hash,
        content_id=content.content_id, text_content=content.text_content,
        auth_manager=manager)


def _report(submission, index, reason=None, status=None):
    account = Account.from_key(bytes([index]) * 32)
    payload = report_payload(
        wallet_address=account.address, submission_id=submission.submission_id,
        content_hash=submission.content_hash,
        reason=reason or REPORT_REASONS[index % len(REPORT_REASONS)],
        nonce=f"nonce-{index}", issued_at="2026-10-10T00:00:00+00:00",
        expires_at="2026-10-10T00:05:00+00:00",
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
    message = report_message(
        wallet_address=payload["wallet_address"], submission_id=payload["submission_id"],
        content_hash=payload["content_hash"], reason=payload["reason"],
        nonce=payload["nonce"], issued_at=payload["issued_at"],
        expires_at=payload["expires_at"], network_id=payload["network_id"])
    signature = _sign(message, account)
    return {"payload": payload, "message": message, "signature": signature,
            "identity": report_identity(payload, signature),
            "reviewer_reference": {"height": 0, "block_hash": "0" * 64,
                                   "status": status or ("ESTABLISHED_REVIEWER" if index == 1 else "PROBATIONARY_REVIEWER")}}


def test_report_domain_and_tampering(blockchain):
    submission = _submission(blockchain)
    report = _report(submission, 1)
    resolver = lambda wallet, height, block_hash: report["reviewer_reference"]["status"]
    assert verify_report(report, submission_id=submission.submission_id,
                         content_hash=submission.content_hash, status_resolver=resolver)
    for field, value in (("reason", REPORT_REASONS[0]), ("submission_id", "other"),
                         ("content_hash", "1" * 64), ("network_id", "wrong"),
                         ("policy_version", 99), ("policy_digest", "0" * 64)):
        changed = deepcopy(report)
        changed["payload"][field] = value
        assert not verify_report(changed, submission_id=submission.submission_id,
                                 content_hash=submission.content_hash, status_resolver=resolver)
    assert report["payload"]["domain"] == "zoidbergchain/community-report/v1"
    assert report["payload"]["policy_digest"] == report_policy_digest()


def test_tally_is_order_independent_and_not_reason_weighted(blockchain):
    submission = _submission(blockchain)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    one = report_tally(reports[:1], submission_id=submission.submission_id,
                       content_hash=submission.content_hash)
    two = report_tally(reports[:2], submission_id=submission.submission_id,
                       content_hash=submission.content_hash)
    three = report_tally(reports, submission_id=submission.submission_id,
                         content_hash=submission.content_hash)
    reverse = report_tally(list(reversed(reports)), submission_id=submission.submission_id,
                           content_hash=submission.content_hash)
    assert not one["threshold_met"] and not two["threshold_met"]
    assert three == reverse and three["threshold_met"]
    assert three["accepted_report_count"] == 3
    assert three["established_reporter_count"] == 1
    assert sum(three["reason_counts"].values()) == 3
    probation = [_report(submission, index, status="PROBATIONARY_REVIEWER") for index in (1, 2, 3)]
    assert not report_tally(probation, submission_id=submission.submission_id,
                            content_hash=submission.content_hash)["threshold_met"]
    conflicting_probation = _report(submission, 1, reason=REPORT_REASONS[-1],
                                    status="PROBATIONARY_REVIEWER")
    with_conflict = report_tally(reports + [conflicting_probation],
                                 submission_id=submission.submission_id,
                                 content_hash=submission.content_hash)
    assert with_conflict["accepted_report_count"] == 3
    assert with_conflict["established_reporter_count"] == 1
    assert with_conflict["threshold_met"]
    counted = next(item for item in with_conflict["report_set"]
                   if item["wallet_address"] == reports[0]["payload"]["wallet_address"])
    assert counted["identity"] == min(reports[0]["identity"], conflicting_probation["identity"])
    assert counted["established_evidence"]["identity"] == reports[0]["identity"]
    low, high = sorted((_report(submission, 1, reason=REPORT_REASONS[0]),
                        _report(submission, 1, reason=REPORT_REASONS[1])),
                       key=lambda record: record["identity"])
    low["reviewer_reference"]["status"] = "PROBATIONARY_REVIEWER"
    high["reviewer_reference"]["status"] = "ESTABLISHED_REVIEWER"
    historical = report_tally([low, high, reports[1], reports[2]],
                              submission_id=submission.submission_id,
                              content_hash=submission.content_hash)
    assert historical["threshold_met"] and historical["established_reporter_count"] == 1
    selected = next(item for item in historical["report_set"]
                    if item["wallet_address"] == low["payload"]["wallet_address"])
    assert selected["identity"] == low["identity"]
    assert selected["established_evidence"]["identity"] == high["identity"]


def test_atomic_report_threshold_and_restart(blockchain, monkeypatch):
    submission = _submission(blockchain)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    statuses = {report["payload"]["wallet_address"]: report["reviewer_reference"]["status"]
                for report in reports}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for index, report in enumerate(reports):
        outcome = blockchain.record_community_report_operation(report)
        assert outcome["action"] == "accepted"
        assert outcome["status"]["threshold_met"] == (index == 2)
    current = blockchain.get_submission(submission.submission_id)
    assert current.status == "quarantined"
    assert blockchain.is_submission_voting_locked(current)
    assert current.quarantine_reason == "community_report_threshold"
    assert current.report_quarantine_evidence["report_set_digest"] == blockchain.report_status(submission.submission_id)["report_set_digest"]
    assert submission.submission_id not in blockchain.mint_queue
    assert blockchain.record_community_report_operation(reports[0])["action"] == "duplicate"
    changed = deepcopy(reports[0]); changed["payload"]["reason"] = REPORT_REASONS[-1]
    with pytest.raises(ValueError):
        blockchain.record_community_report_operation(changed)
    restored = type(blockchain)(storage_backend=blockchain.storage)
    assert restored.report_status(submission.submission_id)["report_set_digest"] == outcome["status"]["report_set_digest"]
    assert restored.get_submission(submission.submission_id).status == "quarantined"
    with pytest.raises(ValueError):
        restored._prepare_certified_commit_request(submission.submission_id, None)
    blockchain.get_submission(submission.submission_id).report_quarantine_evidence["report_set_digest"] = "0" * 64
    with pytest.raises(ValueError, match="quarantine evidence"):
        blockchain.report_status(submission.submission_id)


def test_report_challenge_single_use_and_separate_from_vote(blockchain):
    submission = _submission(blockchain)
    account = Account.from_key(bytes([1]) * 32)
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    challenge = manager.issue_report_challenge(
        wallet_address=account.address, submission_id=submission.submission_id,
        content_hash=submission.content_hash, reason=REPORT_REASONS[0])
    signature = _sign(challenge["message"], account)
    assert manager.verify_report_challenge(
        wallet_address=account.address, message=challenge["message"],
        signature=signature) == challenge["payload"]
    with pytest.raises(ValueError, match="already been used"):
        manager.verify_report_challenge(wallet_address=account.address,
                                        message=challenge["message"], signature=signature)
    with pytest.raises(ValueError):
        manager.verify_vote_signature(wallet_address=account.address,
                                      message=challenge["message"], signature=signature,
                                      submission_id=submission.submission_id,
                                      content_hash=submission.content_hash,
                                      vote_type="not_admissible", dimension="admissibility")


def test_report_api_is_signed_and_separate_from_review(blockchain, monkeypatch):
    from tests.api.test_wallet_auth_api import _client, _verified_headers

    submission = _submission(blockchain)
    account = Account.from_key(bytes([1]) * 32)
    monkeypatch.setattr(blockchain, "get_report_reviewer_decision", lambda wallet: {
        "status": "ESTABLISHED_REVIEWER",
        "reference_finalized_height": 0,
        "reference_finalized_block_hash": blockchain.chain[0].hash,
    })
    monkeypatch.setattr(blockchain, "get_report_reviewer_status_at_reference",
                        lambda wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    client, _ = _client(blockchain)
    headers = _verified_headers(client, account)
    policy = client.get("/reports/policy").json()
    assert policy["policy"]["minimum_valid_reports"] == 3
    unsigned = client.post(f"/submissions/{submission.submission_id}/reports", json={
        "wallet_address": account.address, "message": "unsigned", "signature": "unsigned"})
    assert unsigned.status_code == 401
    challenge = client.post(f"/submissions/{submission.submission_id}/reports/challenge",
        json={"wallet_address": account.address, "submission_id": submission.submission_id,
              "reason": REPORT_REASONS[0]}, headers=headers)
    assert challenge.status_code == 200, challenge.text
    message = challenge.json()["message"]
    request = {"wallet_address": account.address, "message": message,
               "signature": _sign(message, account)}
    accepted = client.post(f"/submissions/{submission.submission_id}/reports",
                           json=request, headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"]["accepted_report_count"] == 1
    assert not accepted.json()["status"]["threshold_met"]
    assert client.post(f"/submissions/{submission.submission_id}/reports",
                       json=request, headers=headers).json()["action"] == "duplicate"
    second_challenge = client.post(f"/submissions/{submission.submission_id}/reports/challenge",
        json={"wallet_address": account.address, "submission_id": submission.submission_id,
              "reason": REPORT_REASONS[1]}, headers=headers)
    assert second_challenge.status_code == 200, second_challenge.text
    second_message = second_challenge.json()["message"]
    conflict = client.post(f"/submissions/{submission.submission_id}/reports",
        json={"wallet_address": account.address, "message": second_message,
              "signature": _sign(second_message, account)}, headers=headers)
    assert conflict.status_code == 200, conflict.text
    assert conflict.json()["action"] == "conflict_recorded"
    status = client.get(f"/submissions/{submission.submission_id}/reports/status").json()
    assert status["accepted_report_count"] == 1
    assert status["observed_report_count"] == 2
    assert blockchain.get_submission_votes(submission.submission_id)["votes"] == []


def test_two_independent_nodes_converge_with_different_report_order(blockchain, isolated_data_dir, monkeypatch):
    from storage import create_storage_backend

    submission = _submission(blockchain)
    initial = deepcopy(blockchain.storage.load_blockchain_state())
    backend = create_storage_backend(
        blockchain_file=str(isolated_data_dir / "peer-blockchain.json"),
        peers_file=str(isolated_data_dir / "peer-peers.json"),
        sqlite_db_path=str(isolated_data_dir / "peer-zoidbergchain.db"))
    backend.save_blockchain_state(initial)
    peer = type(blockchain)(storage_backend=backend)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in reports}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for record in reports:
        blockchain.record_community_report_operation(record)
    for record in reversed(reports):
        peer.record_community_report_operation(record)
    local_status = blockchain.report_status(submission.submission_id)
    peer_status = peer.report_status(submission.submission_id)
    assert local_status["report_set_digest"] == peer_status["report_set_digest"]
    assert local_status["reason_counts"] == peer_status["reason_counts"]
    assert local_status["quarantine_trigger_identity"] == peer_status["quarantine_trigger_identity"]
    assert peer.get_submission(submission.submission_id).status == "quarantined"


def test_adversarial_conflict_orders_retransmit_and_restart_converge(blockchain, isolated_data_dir, monkeypatch):
    from storage import JSONStorageBackend, SQLiteStorageBackend

    submission = _submission(blockchain)
    initial = deepcopy(blockchain.storage.load_blockchain_state())
    nodes = []
    for name, backend_type in (("json", JSONStorageBackend), ("sqlite", SQLiteStorageBackend)):
        backend = backend_type(
            blockchain_file=str(isolated_data_dir / f"conflict-{name}.json"),
            peers_file=str(isolated_data_dir / f"conflict-{name}-peers.json"),
            sqlite_db_path=str(isolated_data_dir / f"conflict-{name}.db"),
        )
        backend.save_blockchain_state(deepcopy(initial))
        nodes.append((type(blockchain)(storage_backend=backend), backend))
    x = _report(submission, 1, reason=REPORT_REASONS[0])
    y = _report(submission, 1, reason=REPORT_REASONS[1])
    second, third = _report(submission, 2), _report(submission, 3)
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in (x, second, third)}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    a, b = (item[0] for item in nodes)
    for record in (x, y, second, third):
        a.record_community_report_operation(record)
    retry = deepcopy(x)
    retry["signature"] = "0x" + retry["signature"].upper().removeprefix("0X")
    retry["untrusted_transport_note"] = "ignored"
    assert a.record_community_report_operation(retry)["action"] == "duplicate"
    for record in (y, x, third, second):
        b.record_community_report_operation(record)
    for source, target in ((a, b), (b, a)):
        for record in source.get_submission(submission.submission_id).community_reports:
            assert target.record_community_report_operation(record)["action"] == "duplicate"
    statuses_after = [node.report_status(submission.submission_id) for node in (a, b)]
    assert statuses_after[0] == statuses_after[1]
    expected = min((x, y), key=lambda record: record["identity"])
    counted = next(item for item in statuses_after[0]["report_set"]
                   if item["wallet_address"] == x["payload"]["wallet_address"])
    assert counted["identity"] == expected["identity"]
    assert statuses_after[0]["accepted_report_count"] == 3
    assert statuses_after[0]["observed_report_count"] == 4
    assert statuses_after[0]["established_reporter_count"] == 1
    assert statuses_after[0]["reason_counts"][expected["payload"]["reason"]] >= 1
    assert statuses_after[0]["threshold_met"]
    assert a.get_submission(submission.submission_id).community_reports == b.get_submission(submission.submission_id).community_reports
    assert a.get_submission(submission.submission_id).report_quarantine_evidence == b.get_submission(submission.submission_id).report_quarantine_evidence
    assert all(node.get_submission(submission.submission_id).quarantine_reason == "community_report_threshold"
               for node in (a, b))
    for node, backend in nodes:
        restarted = type(blockchain)(storage_backend=backend)
        assert restarted.report_status(submission.submission_id) == statuses_after[0]


def test_report_index_avoids_ancestry_walk_for_new_reporters(blockchain, monkeypatch):
    from services.reviewer_eligibility_service import ReviewerEligibilityService
    from services.report_reviewer_index import qualification_snapshot, reference_key, validate_snapshot

    submission = _submission(blockchain)
    accounts = [Account.from_key(bytes([index]) * 32) for index in (1, 2)]
    blocks = [SimpleNamespace(
        index=height, hash=f"{height:064x}",
        creator_wallet=accounts[height // 2].address if height < 4 else None,
        submission_id=f"earned-{height}" if height < 4 else None,
        native_transactions=[],
    ) for height in range(1000)]
    snapshot = qualification_snapshot(blocks, 999, f"{999:064x}")
    key = reference_key(999, f"{999:064x}")
    blockchain.chain = blocks
    blockchain.finalized_blocks = [{"block_height": 999, "block_hash": f"{999:064x}"}]
    blockchain._report_reviewer_index = {key: snapshot}
    assert validate_snapshot(snapshot, blocks, {(999, f"{999:064x}")})
    assert all(snapshot["qualification_heights"][account.address.lower()] == 15 + 2 * index
               for index, account in enumerate(accounts))
    for account in accounts:
        legacy = blockchain._reviewer_eligibility_service.status_at_reference(
            reviewer_address=account.address, chain=blocks,
            finalized_head={"block_height": 999, "block_hash": f"{999:064x}"},
            storage=blockchain.storage,
        )
        assert legacy["status"] == "PROBATIONARY_REVIEWER"
        assert legacy["qualification_effective_height"] == snapshot["qualification_heights"][account.address.lower()]
    walks = []
    def forbidden_walk(*args, **kwargs):
        walks.append(True)
        raise AssertionError("Per-report eligibility traversed finalized ancestry")
    monkeypatch.setattr(ReviewerEligibilityService, "finalized_context", forbidden_walk)
    for index in (1, 1, 2):
        record = _report(submission, index)
        record["reviewer_reference"] = {"height": 999, "block_hash": f"{999:064x}",
                                        "status": "PROBATIONARY_REVIEWER"}
        assert verify_report(record, submission_id=submission.submission_id,
                             content_hash=submission.content_hash,
                             status_resolver=blockchain.get_report_reviewer_status_at_reference)
    assert walks == []
    corrupted = deepcopy(snapshot)
    corrupted["qualification_heights"][accounts[0].address.lower()] = 0
    assert not validate_snapshot(corrupted, blocks, {(999, f"{999:064x}")})
    blockchain._report_reviewer_index = {key: corrupted}
    with pytest.raises(ValueError, match="entry is corrupt"):
        blockchain.get_report_reviewer_status_at_reference(accounts[0].address, 999, f"{999:064x}")
    blockchain._set_report_reviewer_index({key: corrupted}, rebuild=True)
    assert blockchain._report_reviewer_index[key] == snapshot
    blocks[-1].hash = "f" * 64
    with pytest.raises(ValueError, match="missing or stale"):
        blockchain.get_report_reviewer_status_at_reference(accounts[0].address, 999, f"{999:064x}")


@pytest.mark.parametrize("backend_name", ["json", "sqlite"])
def test_finalized_report_index_restart_and_corruption_rebuild(isolated_data_dir, backend_name):
    from blockchain import Blockchain
    from storage import JSONStorageBackend, SQLiteStorageBackend
    from tests.test_milestone_5_task_5_9_release_readiness import _finalize
    from wallet import Wallet

    validators = [Account.create() for _ in range(3)]
    backend_type = JSONStorageBackend if backend_name == "json" else SQLiteStorageBackend
    backend = backend_type(
        blockchain_file=str(isolated_data_dir / f"index-{backend_name}.json"),
        peers_file=str(isolated_data_dir / f"index-{backend_name}-peers.json"),
        sqlite_db_path=str(isolated_data_dir / f"index-{backend_name}.db"),
    )
    kwargs = {"storage_backend": backend,
              "validator_set": tuple(validator.address for validator in validators)}
    node = Blockchain(Wallet(), Wallet(), Wallet(), **kwargs)
    _finalize(node, validators, 0)
    reference = node._report_finalized_head
    key = f'{reference["block_height"]}:{reference["block_hash"]}'
    saved = deepcopy(node._report_reviewer_index[key])
    reviewer = Account.create().address
    assert node.get_report_reviewer_status_at_reference(
        reviewer, reference["block_height"], reference["block_hash"]) == "NEW"
    restarted = Blockchain(**kwargs)
    assert restarted._report_reviewer_index[key] == saved
    assert restarted.get_report_reviewer_status_at_reference(
        reviewer, reference["block_height"], reference["block_hash"]) == "NEW"
    def corrupt(document):
        document["report_reviewer_index"][key]["digest"] = "0" * 64
        return document
    backend.atomic_update_blockchain_document(corrupt)
    rebuilt = Blockchain(**kwargs)
    assert rebuilt._report_reviewer_index[key] == saved
    assert backend.load_blockchain_state()["report_reviewer_index"][key] == saved
    def remove(document):
        document.pop("report_reviewer_index")
        return document
    backend.atomic_update_blockchain_document(remove)
    missing_rebuilt = Blockchain(**kwargs)
    assert missing_rebuilt._report_reviewer_index[key] == saved


def test_threshold_blocks_queued_certificate_without_mutating_it(blockchain, monkeypatch):
    from tests.test_milestone_6_task_6_6_admission import _signed_votes

    submission = _submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    monkeypatch.setattr(type(blockchain), "get_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    frozen = deepcopy(submission.admission_certificate)
    assert submission.status == "queued"
    for index in (1, 2, 3):
        blockchain.record_community_report_operation(_report(submission, index))
    assert submission.status == "quarantined"
    assert submission.admission_certificate == frozen
    assert submission.submission_id not in blockchain.mint_queue
    with pytest.raises(ValueError):
        blockchain.commit_certified_submission(submission.submission_id, validate_meme=False)
    assert blockchain.get_protocol_v1_block_for_submission(submission.submission_id) is None


def test_mint_first_preserves_block_and_rejects_pre_mint_report(blockchain, monkeypatch):
    from tests.test_milestone_6_task_6_6_admission import _signed_votes

    submission = _submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    monkeypatch.setattr(type(blockchain), "get_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    blockchain.commit_certified_submission(submission.submission_id, validate_meme=False)
    minted = blockchain.get_protocol_v1_block_for_submission(submission.submission_id)
    assert minted is not None
    with pytest.raises(ValueError, match="Post-mint dispute flow required"):
        blockchain.record_community_report_operation(_report(submission, 1))
    assert blockchain.get_protocol_v1_block_for_submission(submission.submission_id).hash == minted.hash
    assert blockchain.report_status(submission.submission_id)["accepted_report_count"] == 0


def test_sqlite_report_round_trip(blockchain, isolated_data_dir, monkeypatch):
    from storage import SQLiteStorageBackend

    submission = _submission(blockchain)
    backend = SQLiteStorageBackend(
        blockchain_file=str(isolated_data_dir / "sqlite-blockchain.json"),
        peers_file=str(isolated_data_dir / "sqlite-peers.json"),
        sqlite_db_path=str(isolated_data_dir / "reports.db"))
    backend.save_blockchain_state(deepcopy(blockchain.storage.load_blockchain_state()))
    node = type(blockchain)(storage_backend=backend)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in reports}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for report in reports:
        node.record_community_report_operation(report)
    restarted = type(blockchain)(storage_backend=backend)
    assert restarted.get_submission(submission.submission_id).status == "quarantined"
    assert restarted.report_status(submission.submission_id)["report_set_digest"] == node.report_status(submission.submission_id)["report_set_digest"]


def test_concurrent_threshold_and_mint_have_one_committed_winner(blockchain, monkeypatch):
    from tests.test_milestone_6_task_6_6_admission import _signed_votes

    submission = _submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    for index in (1, 2):
        blockchain.record_community_report_operation(_report(submission, index))
    minter = type(blockchain)(storage_backend=blockchain.storage)
    barrier = Barrier(2)

    def report():
        barrier.wait()
        try:
            return blockchain.record_community_report_operation(_report(submission, 3))
        except ValueError:
            return None

    def mint():
        barrier.wait()
        try:
            minter.commit_certified_submission(submission.submission_id, validate_meme=False)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        report_future = pool.submit(report)
        mint_future = pool.submit(mint)
        reported = report_future.result()
        minted = mint_future.result()
    latest = type(blockchain)(storage_backend=blockchain.storage)
    if reported is not None:
        assert reported["status"]["threshold_met"]
        assert not minted
        assert latest.get_submission(submission.submission_id).status == "quarantined"
        assert latest.get_protocol_v1_block_for_submission(submission.submission_id) is None
    else:
        assert minted
        assert latest.get_submission(submission.submission_id).status == "minted"
        assert latest.get_protocol_v1_block_for_submission(submission.submission_id) is not None


def test_stale_ordinary_save_cannot_erase_committed_report_quarantine(blockchain, monkeypatch):
    submission = _submission(blockchain)
    stale = type(blockchain)(storage_backend=blockchain.storage)
    reports = [_report(submission, index) for index in (1, 2, 3)]
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in reports}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for report in reports:
        blockchain.record_community_report_operation(report)
    with pytest.raises(ValueError, match="Stale community reporting state"):
        stale.save_blockchain()
    final = type(blockchain)(storage_backend=blockchain.storage)
    assert final.get_submission(submission.submission_id).status == "quarantined"
    assert final.report_status(submission.submission_id)["accepted_report_count"] == 3
    assert submission.submission_id not in final.mint_queue


def test_later_report_updates_canonical_threshold_trigger(blockchain, monkeypatch):
    submission = _submission(blockchain)
    reports = [_report(submission, index) for index in (1, 2, 3, 4)]
    statuses = {record["payload"]["wallet_address"]: record["reviewer_reference"]["status"]
                for record in reports}
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    for report in reports[:3]:
        blockchain.record_community_report_operation(report)
    first = deepcopy(submission.report_quarantine_evidence)
    blockchain.record_community_report_operation(reports[3])
    current = blockchain.report_status(submission.submission_id)
    evidence = submission.report_quarantine_evidence
    assert submission.status == "quarantined"
    assert current["accepted_report_count"] == 4
    assert evidence["report_set_digest"] == current["report_set_digest"]
    assert evidence["report_set_digest"] != first["report_set_digest"]
    assert evidence["canonical_trigger_report_set"] == current["canonical_trigger_report_set"]
    assert evidence["canonical_trigger_report_set_digest"] == current["canonical_trigger_report_set_digest"]
    restored = type(blockchain)(storage_backend=blockchain.storage)
    assert restored.get_submission(submission.submission_id).report_quarantine_evidence == evidence


def test_concurrent_exact_retry_counts_once(blockchain, monkeypatch):
    submission = _submission(blockchain)
    report = _report(submission, 1)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(blockchain.record_community_report_operation, [report, report]))
    assert {result["action"] for result in results} == {"accepted", "duplicate"}
    assert type(blockchain)(storage_backend=blockchain.storage).report_status(
        submission.submission_id)["accepted_report_count"] == 1


def test_ineligible_or_bad_signature_cannot_enter_report_set(blockchain, monkeypatch):
    submission = _submission(blockchain)
    report = _report(submission, 1)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "NEW")
    with pytest.raises(ValueError, match="reporter eligibility"):
        blockchain.record_community_report_operation(report)
    monkeypatch.setattr(type(blockchain), "get_report_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: "ESTABLISHED_REVIEWER")
    altered = deepcopy(report)
    altered["signature"] = _report(submission, 2)["signature"]
    with pytest.raises(ValueError, match="Invalid signed report"):
        blockchain.record_community_report_operation(altered)
    assert blockchain.report_status(submission.submission_id)["accepted_report_count"] == 0


def test_report_rebroadcast_requires_verified_wallet(blockchain):
    from tests.api.test_wallet_auth_api import _client

    submission = _submission(blockchain)
    client, _ = _client(blockchain)
    response = client.post(f"/submissions/{submission.submission_id}/reports/broadcast")
    assert response.status_code == 401

