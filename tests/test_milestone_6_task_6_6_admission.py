from __future__ import annotations

import copy
import hashlib

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from admission_certificate import build_admission_certificate, validate_admission_certificate
from blockchain import Blockchain
from dual_review import ADMISSIBILITY, ORIGINALITY, vote_identity, vote_message
from milestone5_policy import REPUTATION_RULE_VERSION
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, canonical_hash
from wallet_auth import WalletAuthManager


def _signed(message, account):
    return Account.sign_message(encode_defunct(text=message), account.key).signature.hex()


def _current_submission(chain):
    account = Account.from_key(bytes.fromhex("aa" * 32))
    content = chain.upload_text_content_operation(text_content="Task 6.6 admitted media", submitted_by=account.address)
    evidence = chain.technical_validation_evidence_for_content(content)
    manager = WalletAuthManager(network_name="zoidberg-testnet", environment="development")
    challenge = manager.issue_submission_challenge(wallet_address=account.address,
        content_hash=content.content_hash, content_id=content.content_id,
        caption="", technical_validation=evidence)
    submission = chain.submit_signed_content_operation(wallet_address=account.address,
        message=challenge["message"], signature=_signed(challenge["message"], account),
        content_hash=content.content_hash, content_id=content.content_id,
        text_content=content.text_content, auth_manager=manager)
    return submission, content, evidence


def _signed_votes(chain, submission, *, originality="original", admissibility="admissible"):
    statuses = {}
    votes = []
    for index in range(5):
        account = Account.from_key(bytes([index + 1]) * 32)
        wallet = account.address.lower()
        status = "ESTABLISHED_REVIEWER" if index == 0 else "PROBATIONARY_REVIEWER"
        statuses[wallet] = status
        for dimension, choice in ((ORIGINALITY, originality), (ADMISSIBILITY, admissibility)):
            payload = dict(wallet_address=wallet, submission_id=submission.submission_id,
                content_hash=submission.content_hash, dimension=dimension, choice=choice,
                nonce=f"vote-{index}-{dimension}", issued_at="2026-10-01T00:00:00Z",
                expires_at="2026-10-01T01:00:00Z", network_id=PUBLIC_TESTNET_V1_NETWORK_ID)
            message = vote_message(**payload)
            signature = _signed(message, account)
            votes.append(dict(voter=wallet, voter_wallet_address=wallet,
                submission_id=submission.submission_id, content_hash=submission.content_hash,
                vote_type=choice, dimension=dimension, vote_version=2, protocol_version=1,
                network_id=PUBLIC_TESTNET_V1_NETWORK_ID, signature_scheme="personal_sign",
                vote_signature=signature, vote_message=message, vote_nonce=payload["nonce"],
                signed_message_hash=hashlib.sha256(message.encode()).hexdigest(),
                vote_issued_at=payload["issued_at"], vote_expires_at=payload["expires_at"],
                vote_identity=vote_identity(signature=signature, **payload),
                reviewer_policy_version=1, reputation_rule_version=REPUTATION_RULE_VERSION, reviewer_status=status,
                reviewer_eligible=True, reviewer_status_effective_height=0,
                reviewer_status_reference_block_hash=chain.chain[0].hash))
    return votes, statuses


def test_certificate_is_frozen_canonical_and_revalidates_after_restart(blockchain, monkeypatch):
    submission, content, evidence = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    resolver = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.get_reviewer_status_at_reference = resolver
    blockchain.votes.extend(reversed(votes))
    from content import load_content_bytes
    media = load_content_bytes(content.content_hash, content.mime_type, data_dir=blockchain.storage.data_dir)
    certificate = build_admission_certificate(submission_id=submission.submission_id,
        content_hash=submission.content_hash, creator_wallet=submission.submitter,
        media_bytes=media, technical_evidence=evidence,
        attestation=submission.submitter_attestation, votes=votes,
        reviewer_status_resolver=resolver)
    reverse = build_admission_certificate(submission_id=submission.submission_id,
        content_hash=submission.content_hash, creator_wallet=submission.submitter,
        media_bytes=media, technical_evidence=evidence,
        attestation=submission.submitter_attestation, votes=list(reversed(votes)),
        reviewer_status_resolver=resolver)
    assert certificate == reverse
    alternate_transport = copy.deepcopy(votes)
    alternate_transport[0]["vote_signature"] = alternate_transport[0]["vote_signature"].upper()
    alternate_transport[0]["voter"] = alternate_transport[0]["voter"].upper().replace("0X", "0x")
    alternate_transport[0]["voter_wallet_address"] = alternate_transport[0]["voter_wallet_address"].upper().replace("0X", "0x")
    assert build_admission_certificate(submission_id=submission.submission_id,
        content_hash=submission.content_hash, creator_wallet=submission.submitter,
        media_bytes=media, technical_evidence=evidence,
        attestation=submission.submitter_attestation, votes=alternate_transport,
        reviewer_status_resolver=resolver) == certificate
    evaluation, queued, view = blockchain.evaluate_submission_operation(submission.submission_id)
    assert queued.status == "queued"
    assert view.certificate_id == certificate["certificate_digest"]
    frozen = copy.deepcopy(queued.admission_certificate)
    blockchain.votes.append(dict(votes[0], vote_identity="later-duplicate"))
    assert queued.admission_certificate == frozen
    monkeypatch.setattr(Blockchain, "get_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    restored = Blockchain(storage_backend=blockchain.storage)
    restored.get_reviewer_status_at_reference = resolver
    assert restored.get_submission(submission.submission_id).admission_certificate == frozen
    assert restored.admission_status(restored.get_submission(submission.submission_id))["state"] == "mintable"
    invalid = copy.deepcopy(frozen)
    invalid["admissibility"]["outcome"] = "not_admissible"
    with pytest.raises(ValueError):
        validate_admission_certificate(invalid, media_bytes=media, reviewer_status_resolver=resolver)


def test_current_mint_embeds_admission_and_peer_can_validate(blockchain):
    submission, content, evidence = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    assert blockchain._evaluate_mint_queue_item(submission.submission_id)["mintable"]
    assert blockchain.mint_submission(submission.submission_id, validate_meme=False)
    block = blockchain.chain[-1]
    assert block.block_version == 2
    assert block.media_bytes == b"Task 6.6 admitted media"
    assert block.admission_certificate["certificate_digest"] == block.certificate_id
    assert blockchain.is_chain_valid(blockchain.get_chain())
    tampered = block.to_dict()
    tampered["admission_certificate"] = dict(tampered["admission_certificate"], policy_version=999)
    with pytest.raises(ValueError):
        blockchain.validate_block_certificate_metadata(tampered, prior_chain=blockchain.chain[:-1])


@pytest.mark.parametrize("dimension,choice,reason", [
    (ORIGINALITY, "not_original", "review_rejected_originality"),
    (ADMISSIBILITY, "not_admissible", "review_rejected_admissibility"),
])
def test_negative_review_quarantines_before_queue(blockchain, dimension, choice, reason):
    submission, _, _ = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission,
        originality=choice if dimension == ORIGINALITY else "original",
        admissibility=choice if dimension == ADMISSIBILITY else "admissible")
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    evaluation, evaluated, certificate = blockchain.evaluate_submission_operation(submission.submission_id)
    assert evaluated.status == "quarantined"
    assert evaluated.quarantine_reason == reason
    assert certificate is None
    assert submission.submission_id not in blockchain.mint_queue
    with pytest.raises(ValueError):
        blockchain.add_to_mint_queue(submission.submission_id)
    restored = Blockchain(storage_backend=blockchain.storage)
    assert restored.get_submission(submission.submission_id).quarantine_reason == reason


def test_originality_only_and_stale_queue_cannot_mint_current_submission(blockchain):
    submission, _, _ = _current_submission(blockchain)
    submission.status = "approved"
    with pytest.raises(ValueError, match="frozen admission certificate"):
        blockchain.add_to_mint_queue(submission.submission_id)
    submission.status = "queued"
    blockchain.mint_queue.append(submission.submission_id)
    blockchain.save_blockchain()
    restored = Blockchain(storage_backend=blockchain.storage)
    pending = restored.get_submission(submission.submission_id)
    assert pending.status == "quarantined"
    assert pending.quarantine_reason == "invalid_admission_on_restart"
    assert submission.submission_id not in restored.mint_queue


def test_peer_verifies_embedded_admission_without_local_submission(blockchain, tmp_path):
    from peer_sync import MalformedBlockError, receive_peer_block
    from peers import PeerStore
    from storage import JSONStorageBackend

    submission, _, _ = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    resolver = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.get_reviewer_status_at_reference = resolver
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    assert blockchain.mint_submission(submission.submission_id, validate_meme=False)
    block = blockchain.chain[-1]

    peer_dir = tmp_path / "peer"
    peer_dir.mkdir()
    backend = JSONStorageBackend(blockchain_file=str(peer_dir / "chain.json"),
                                 peers_file=str(peer_dir / "peers.json"))
    peer = Blockchain(project_owner_wallet=blockchain.project_owner_wallet,
                      Contributor_one=blockchain.Contributor_one,
                      Contributor_two=blockchain.Contributor_two, storage_backend=backend)
    peer.get_reviewer_status_at_reference = resolver
    store = PeerStore(storage_backend=backend)
    store.register_peer(node_id="source", url="http://source.test:8000", network_name="zoidberg-testnet")
    forged = block.to_dict()
    forged.pop("admission_certificate")
    with pytest.raises(MalformedBlockError):
        receive_peer_block(peer, store, "source", "zoidberg-testnet", forged,
                           submission.submission_id, "zoidberg-testnet")
    received = receive_peer_block(peer, store, "source", "zoidberg-testnet", block.to_dict(),
                                  submission.submission_id, "zoidberg-testnet")
    assert received["accepted"] is True
    assert peer.chain[-1].hash == block.hash


def test_sqlite_roundtrip_preserves_admission_and_quarantine(isolated_data_dir, wallets, monkeypatch):
    from storage import SQLiteStorageBackend

    backend = SQLiteStorageBackend(
        blockchain_file=str(isolated_data_dir / "admission.json"),
        peers_file=str(isolated_data_dir / "admission-peers.json"),
        sqlite_db_path=str(isolated_data_dir / "admission.db"),
    )
    chain = Blockchain(project_owner_wallet=wallets["owner"],
                       Contributor_one=wallets["contributor_one"],
                       Contributor_two=wallets["contributor_two"], storage_backend=backend)
    submission, _, _ = _current_submission(chain)
    votes, statuses = _signed_votes(chain, submission)
    monkeypatch.setattr(Blockchain, "get_reviewer_status_at_reference",
                        lambda self, wallet, height, block_hash: statuses[wallet])
    chain.votes.extend(votes)
    chain.evaluate_submission_operation(submission.submission_id)
    digest = chain.get_submission(submission.submission_id).admission_certificate["certificate_digest"]
    restored = Blockchain(storage_backend=backend)
    current = restored.get_submission(submission.submission_id)
    assert current.admission_certificate["certificate_digest"] == digest
    assert restored.admission_status(current)["state"] == "mintable"

    current.admission_certificate["policy_digest"] = "0" * 64
    restored.save_blockchain()
    quarantined = Blockchain(storage_backend=backend)
    pending = quarantined.get_submission(submission.submission_id)
    assert pending.status == "quarantined"
    assert pending.quarantine_reason == "invalid_admission_on_restart"
    assert submission.submission_id not in quarantined.mint_queue


def test_tampered_queued_admission_is_removed_before_commit(blockchain):
    submission, _, _ = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    submission.admission_certificate["policy_digest"] = "0" * 64
    blockchain.save_blockchain()
    head = blockchain.chain[-1].hash
    with pytest.raises(ValueError):
        blockchain.commit_certified_submission(submission.submission_id)
    assert blockchain.chain[-1].hash == head
    assert blockchain.get_submission(submission.submission_id).status == "quarantined"
    assert submission.submission_id not in blockchain.mint_queue


def test_evaluating_tampered_frozen_admission_persists_quarantine(blockchain):
    submission, _, _ = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    blockchain.get_reviewer_status_at_reference = lambda wallet, height, block_hash: statuses[wallet]
    blockchain.votes.extend(votes)
    blockchain.evaluate_submission_operation(submission.submission_id)
    submission.admission_certificate["policy_digest"] = "0" * 64

    result = blockchain.evaluate_submission(submission.submission_id)

    assert result["status"] == "quarantined"
    assert submission.quarantine_reason == "invalid_frozen_admission_evidence"
    assert submission.submission_id not in blockchain.mint_queue


@pytest.mark.parametrize("path,value", [
    (("certificate_version",), 99),
    (("network_id",), "other-network"),
    (("submission_id",), "f" * 32),
    (("content_hash",), "0" * 64),
    (("policy_digest",), "0" * 64),
    (("technical_evidence_version",), 99),
    (("technical_evidence", "evidence_digest"), "0" * 64),
    (("attestation_version",), 99),
    (("attestation", "signature"), "0x" + "00" * 65),
    (("review_policy_digest",), "0" * 64),
    (("originality", "outcome"), "not_original"),
    (("admissibility", "outcome"), "not_admissible"),
])
def test_forged_certificate_fields_fail_even_with_recomputed_digest(blockchain, path, value):
    from content import load_content_bytes

    submission, content, evidence = _current_submission(blockchain)
    votes, statuses = _signed_votes(blockchain, submission)
    resolver = lambda wallet, height, block_hash: statuses[wallet]
    media = load_content_bytes(content.content_hash, content.mime_type, data_dir=blockchain.storage.data_dir)
    certificate = build_admission_certificate(submission_id=submission.submission_id,
        content_hash=submission.content_hash, creator_wallet=submission.submitter,
        media_bytes=media, technical_evidence=evidence,
        attestation=submission.submitter_attestation, votes=votes,
        reviewer_status_resolver=resolver)
    forged = copy.deepcopy(certificate)
    target = forged
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    forged["certificate_digest"] = canonical_hash({k: v for k, v in forged.items() if k != "certificate_digest"})
    with pytest.raises(ValueError):
        validate_admission_certificate(forged, media_bytes=media, reviewer_status_resolver=resolver)
