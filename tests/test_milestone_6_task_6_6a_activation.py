from __future__ import annotations

import copy
import json

import pytest

from blockchain import Blockchain
from storage import JSONStorageBackend, SQLiteStorageBackend
from tests.blockchain.test_protocol_v1_block_format import _mint_protocol_v1_block
from tests.test_milestone_6_task_6_6_admission import _current_submission, _signed_votes


def test_activation_height_is_exact_and_historical_v1_hash_is_unchanged(blockchain, submission_image, wallets):
    _submission, _certificate, legacy = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    old_hash = legacy.hash
    assert blockchain.configure_admission_activation()["activation_height"] == 2
    assert blockchain.admission_activation_status()["last_legacy_height"] == 1
    assert blockchain.is_chain_valid(blockchain.get_chain())
    assert legacy.hash == old_hash

    for illegal_height in (2, 3):
        forged = legacy.to_dict()
        forged["index"] = illegal_height
        forged["hash"] = blockchain.calculate_hash_from_dict(forged)
        with pytest.raises(ValueError, match="Post-activation"):
            blockchain._block_validation_service.validate_block(
                forged, blockchain._block_validation_collaborators(),
                prior_chain=blockchain.get_chain())


def test_v2_at_activation_and_mixed_history_validate(blockchain, submission_image, wallets):
    _mint_protocol_v1_block(blockchain, submission_image, wallets)
    blockchain.configure_admission_activation()
    submission, _, _ = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    assert blockchain.mint_submission(submission.submission_id, validate_meme=False)
    assert [block.block_version for block in blockchain.chain[1:]] == [1, 2]
    assert blockchain.is_chain_valid(blockchain.get_chain())
    tampered = blockchain.get_chain()
    tampered[2]["admission_certificate"] = None
    assert not blockchain.is_chain_valid(tampered)
    illegal = blockchain.get_chain()
    illegal[2]["block_version"] = 1
    assert not blockchain.is_chain_valid(illegal)
    assert blockchain.admission_activation_status()["state"] == "active"
    blockchain._admission_activation_store.path.unlink()
    assert blockchain.admission_activation_status()["state"] == "misconfigured"
    with pytest.raises(ValueError, match="changed or disappeared"):
        blockchain.require_admission_activation_for_new_block()
    with pytest.raises(ValueError, match="activation"):
        Blockchain(storage_backend=blockchain.storage)


@pytest.mark.parametrize("backend_type", [JSONStorageBackend, SQLiteStorageBackend])
def test_activation_persists_and_rejects_rollback(isolated_data_dir, wallets, backend_type):
    backend = backend_type(blockchain_file=str(isolated_data_dir / "activation-chain.json"),
                           peers_file=str(isolated_data_dir / "activation-peers.json"))
    chain = Blockchain(project_owner_wallet=wallets["owner"],
                       Contributor_one=wallets["contributor_one"],
                       Contributor_two=wallets["contributor_two"], storage_backend=backend)
    status = chain.configure_admission_activation()
    assert status["activation_height"] == 1
    restored = Blockchain(storage_backend=backend)
    assert restored.admission_activation_status()["activation_height"] == 1
    with pytest.raises(ValueError, match="immutable"):
        restored.configure_admission_activation(2)
    record_path = restored._admission_activation_store.path
    original = record_path.read_text(encoding="utf-8")
    record_path.unlink()
    with pytest.raises(ValueError, match="activation"):
        Blockchain(storage_backend=backend)
    record_path.write_text(original, encoding="utf-8")
    changed = json.loads(original)
    changed["activation_height"] = 2
    record_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="activation"):
        Blockchain(storage_backend=backend)


def test_unset_public_testnet_cannot_accept_new_block(blockchain, monkeypatch):
    import blockchain as blockchain_module
    monkeypatch.setattr(blockchain_module, "ENVIRONMENT", "testnet")
    assert blockchain.admission_activation_status()["state"] == "misconfigured"
    with pytest.raises(ValueError, match="configured admission activation"):
        blockchain.require_admission_activation_for_new_block()
    candidate = copy.deepcopy(blockchain.get_chain())
    candidate.append(dict(candidate[0], index=1, hash="new"))
    assert not blockchain.is_chain_valid(candidate)


def test_pending_legacy_originality_certificate_cannot_mint_after_activation(blockchain, submission_image, wallets):
    from tests.blockchain.test_protocol_v1_block_format import _certified_submission

    submission, certificate = _certified_submission(blockchain, submission_image, wallets)
    assert certificate is not None
    blockchain.configure_admission_activation()
    assert not blockchain._evaluate_mint_queue_item(submission.submission_id)["mintable"]
    with pytest.raises(ValueError, match="Post-activation"):
        blockchain.mint_submission(submission.submission_id, validate_meme=False)
    restored = Blockchain(storage_backend=blockchain.storage)
    assert submission.submission_id not in restored.mint_queue
    assert restored.get_submission(submission.submission_id).status == "approved"


def test_pre_activation_pending_submission_can_complete_signed_current_admission(blockchain):
    from eth_account import Account
    from submission import ATTESTATION_LEGACY
    from tests.test_milestone_6_task_6_6_admission import _signed
    from wallet_auth import WalletAuthManager

    account = Account.from_key(bytes.fromhex("ab" * 32))
    content = blockchain.upload_text_content_operation(
        text_content="Legacy pending media admitted after activation", submitted_by=account.address)
    legacy = blockchain.submit_existing_content(
        content_hash=content.content_hash, content_id=content.content_id,
        submitter=account.address, text_content=content.text_content,
        attestation_requirement=ATTESTATION_LEGACY)
    blockchain.save_blockchain()
    blockchain.configure_admission_activation()
    with pytest.raises(ValueError, match="Post-activation"):
        blockchain.require_valid_certificate_for_submission(legacy)

    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    evidence = blockchain.technical_validation_evidence_for_content(content)
    challenge = manager.issue_submission_challenge(
        wallet_address=account.address, content_hash=content.content_hash,
        content_id=content.content_id, technical_validation=evidence,
        submission_id=legacy.submission_id)
    upgraded = blockchain.attach_current_admission_attestation_operation(
        submission_id=legacy.submission_id, wallet_address=account.address,
        message=challenge["message"], signature=_signed(challenge["message"], account),
        auth_manager=manager)
    assert upgraded.submission_id == legacy.submission_id
    assert upgraded.attestation_requirement == "public_testnet_v1_required"
    votes, statuses = _signed_votes(blockchain, upgraded)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(upgraded.submission_id)
    assert blockchain.mint_submission(upgraded.submission_id, validate_meme=False)
    assert blockchain.chain[-1].block_version == 2


def test_peer_v1_boundary_and_v2_acceptance(isolated_data_dir, wallets, submission_image):
    from peer_sync import MalformedBlockError, WrongNetworkError, receive_peer_block
    from peers import PeerStore

    def node(name):
        directory = isolated_data_dir / name
        directory.mkdir()
        backend = JSONStorageBackend(blockchain_file=str(directory / "blockchain.json"),
                                     peers_file=str(directory / "peers.json"))
        chain = Blockchain(project_owner_wallet=wallets["owner"],
                           Contributor_one=wallets["contributor_one"],
                           Contributor_two=wallets["contributor_two"], storage_backend=backend)
        store = PeerStore(storage_backend=backend)
        store.register_peer(node_id="source", url="http://source.test:8000", network_name="zoidberg-testnet")
        return chain, store

    legacy_source, _ = node("legacy-source")
    _submission, _certificate, legacy = _mint_protocol_v1_block(
        legacy_source, submission_image, wallets)
    permitted, permitted_store = node("permitted")
    permitted.configure_admission_activation(2)
    permitted.originality_certificates = copy.deepcopy(legacy_source.originality_certificates)
    permitted.originality_evidence = copy.deepcopy(legacy_source.originality_evidence)
    assert receive_peer_block(permitted, permitted_store, "source", "zoidberg-testnet",
                              legacy.to_dict(), legacy.submission_id, "zoidberg-testnet",
                              peer_activation_height=2)["accepted"]

    blocked, blocked_store = node("blocked")
    blocked.configure_admission_activation(1)
    blocked.originality_certificates = copy.deepcopy(legacy_source.originality_certificates)
    blocked.originality_evidence = copy.deepcopy(legacy_source.originality_evidence)
    with pytest.raises(WrongNetworkError, match="activation height"):
        receive_peer_block(blocked, blocked_store, "source", "zoidberg-testnet",
                           legacy.to_dict(), legacy.submission_id, "zoidberg-testnet",
                           peer_activation_height=2)
    with pytest.raises(MalformedBlockError):
        receive_peer_block(blocked, blocked_store, "source", "zoidberg-testnet",
                           legacy.to_dict(), legacy.submission_id, "zoidberg-testnet",
                           peer_activation_height=1)

    admitted_source, _ = node("admitted-source")
    admitted_source.configure_admission_activation(1)
    submission, _, _ = _current_submission(admitted_source)
    votes, statuses = _signed_votes(admitted_source, submission)
    resolver = lambda wallet, height, block_hash: statuses[wallet]
    admitted_source.get_reviewer_status_at_reference = resolver
    admitted_source.votes.extend(votes)
    admitted_source.evaluate_submission_operation(submission.submission_id)
    assert admitted_source.mint_submission(submission.submission_id, validate_meme=False)
    admitted_peer, admitted_store = node("admitted-peer")
    admitted_peer.configure_admission_activation(1)
    admitted_peer.get_reviewer_status_at_reference = resolver
    assert receive_peer_block(admitted_peer, admitted_store, "source", "zoidberg-testnet",
                              admitted_source.chain[-1].to_dict(), submission.submission_id,
                              "zoidberg-testnet", peer_activation_height=1)["accepted"]


def test_reorg_and_peer_summary_reject_conflicting_activation(blockchain, submission_image, wallets):
    from services.peer_chain_sync_service import (
        ChainSyncCollaborators, ChainSyncState, PeerChainSyncService)

    _submission, _certificate, legacy = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    blockchain.configure_admission_activation()
    candidate = blockchain.get_chain()
    illegal = legacy.to_dict()
    illegal["index"] = 2
    illegal["previous_hash"] = legacy.hash
    illegal["hash"] = blockchain.calculate_hash_from_dict(illegal)
    candidate.append(illegal)
    comparison = blockchain.compare_chains_by_originality(blockchain.chain, candidate)
    assert comparison["decision"] == "invalid_candidate"

    service = PeerChainSyncService(transport=None, build_headers=None, logger=None)
    service.fetch_summary = lambda *args, **kwargs: {
        "network_name": "zoidberg-testnet", "network_id": blockchain.protocol_v1_network_id(),
        "genesis_hash": blockchain.chain[0].hash, "chain_height": 1,
        "latest_block_hash": "different", "cumulative_originality_score": 0,
        "admission_activation_height": 3,
    }
    state = ChainSyncState(local_height=1, local_latest_hash=blockchain.chain[-1].hash,
                           local_genesis_hash=blockchain.chain[0].hash, local_score=0,
                           local_network_id=blockchain.protocol_v1_network_id(),
                           admission_activation_height=2)
    collaborators = ChainSyncCollaborators(
        compare_summaries=lambda **kwargs: pytest.fail("Conflicting peer reached fork choice"),
        store_certificates=lambda *args: None, store_evidence=lambda *args: None,
        validate_candidate=lambda *args, **kwargs: [],
        compare_candidate=lambda *args: {}, adopt_candidate=lambda *args: {})
    result = service.sync_peer(
        {"node_id": "conflict", "url": "http://peer.test"},
        origin_node_id="local", network_name="zoidberg-testnet", timeout_seconds=1,
        state=state, collaborators=collaborators)
    assert result["reason"] == "conflicting_admission_activation"


def test_operator_status_and_signed_pending_transition_api(blockchain):
    from eth_account import Account
    from submission import ATTESTATION_LEGACY
    from tests.api.test_wallet_auth_api import _client, _sign_message, _verified_headers

    account = Account.from_key(bytes.fromhex("ac" * 32))
    content = blockchain.upload_text_content_operation(
        text_content="Signed pending upgrade API", submitted_by=account.address)
    legacy = blockchain.submit_existing_content(
        content_hash=content.content_hash, content_id=content.content_id,
        submitter=account.address, text_content=content.text_content,
        attestation_requirement=ATTESTATION_LEGACY)
    blockchain.save_blockchain()
    blockchain.configure_admission_activation()
    client, _manager = _client(blockchain)
    status = client.get("/status")
    assert status.status_code == 200
    assert status.json()["admission_activation"]["activation_height"] == 1
    headers = _verified_headers(client, account)
    challenge = client.post("/auth/wallet/submission-challenge", json={
        "wallet_address": account.address, "content_hash": content.content_hash,
        "content_id": content.content_id, "submission_id": legacy.submission_id,
    }, headers=headers)
    assert challenge.status_code == 200
    assert challenge.json()["submission_id"] == legacy.submission_id
    attached = client.post(f"/submissions/{legacy.submission_id}/admission-attestation", json={
        "wallet_address": account.address, "message": challenge.json()["message"],
        "signature": _sign_message(challenge.json()["message"], account),
    }, headers=headers)
    assert attached.status_code == 200
    assert attached.json()["submission"]["admission"]["state"] == "awaiting_review"


def test_operator_cli_fixes_tip_plus_one_once(blockchain, monkeypatch, capsys):
    from scripts import configure_admission_activation as command

    monkeypatch.setattr(command, "create_storage_backend", lambda: blockchain.storage)
    assert command.main(["--next-block"]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert first["canonical_tip_height"] == 0
    assert first["activation_height"] == 1
    assert command.main(["--show"]) == 0
    shown = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert shown["activation_height"] == 1
    with pytest.raises(ValueError, match="immutable"):
        command.main(["--height", "2"])
