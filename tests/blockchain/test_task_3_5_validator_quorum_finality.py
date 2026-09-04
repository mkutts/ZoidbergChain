from copy import deepcopy

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain import Blockchain
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_finality import (
    build_protocol_v1_finality_attestation,
    build_protocol_v1_finality_attestation_message,
)
from services import FinalityAttestationError, FinalityService, required_quorum
from storage import create_storage_backend
import config


def _accounts(count=3):
    return [Account.create() for _ in range(count)]


def _attestation(account, *, height, block_hash, network_id=PUBLIC_TESTNET_V1_NETWORK_ID):
    message = build_protocol_v1_finality_attestation_message(
        validator_address=account.address, block_height=height, block_hash=block_hash,
        network_id=network_id,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_protocol_v1_finality_attestation(
        validator_address=account.address, block_height=height, block_hash=block_hash,
        network_id=network_id, signature=signature,
    )


@pytest.mark.parametrize("count, expected", [(1, 1), (2, 2), (3, 2), (4, 3), (5, 4), (6, 4), (7, 5)])
def test_validator_quorum_is_ceiling_of_two_thirds(count, expected):
    assert required_quorum(count) == expected


def test_validator_configuration_normalizes_duplicates_and_rejects_malformed_entries():
    address = "0x" + "a" * 40
    assert config._parse_validator_addresses(f"0x{'A' * 40}, {address}") == (address,)
    with pytest.raises(ValueError, match="Ethereum-style"):
        config._parse_validator_addresses("not-an-address")
    with pytest.raises(ValueError, match="empty entries"):
        config._parse_validator_addresses(f"{address},")


def test_quorum_finality_is_authoritative_durable_and_idempotent(blockchain, wallets):
    validators = _accounts()
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    block = blockchain.get_latest_block()

    first = blockchain.submit_validator_finality_attestation(
        _attestation(validators[0], height=block.index, block_hash=block.hash)
    )
    assert first["vote_count"] == 1
    assert blockchain.get_block_chain_state(block.hash)["finalized"] is False

    second = blockchain.submit_validator_finality_attestation(
        _attestation(validators[1], height=block.index, block_hash=block.hash)
    )
    assert second["vote_count"] == 2
    assert second["finalization"]["required_quorum"] == 2
    assert blockchain.get_block_chain_state(block.hash)["finalized"] is True

    duplicate = blockchain.submit_validator_finality_attestation(
        _attestation(validators[1], height=block.index, block_hash=block.hash)
    )
    assert duplicate["status"] == "duplicate"
    assert len(blockchain.finality_attestations) == 2
    assert blockchain.get_finality_evidence(block.hash)["validator_set"] == list(blockchain.validator_set)

    reloaded = Blockchain(
        wallets["owner"], wallets["contributor_one"], wallets["contributor_two"],
        storage_backend=blockchain.storage, validator_set=blockchain.validator_set,
    )
    assert reloaded.get_block_chain_state(block.hash)["finalized"] is True
    assert reloaded.get_finality_evidence(block.hash)["attestations"] == blockchain.get_finality_evidence(block.hash)["attestations"]


def test_attestation_rejects_unknown_bad_domain_bad_signature_and_noncanonical_target(blockchain):
    validators = _accounts()
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    block = blockchain.get_latest_block()

    unknown = _attestation(Account.create(), height=block.index, block_hash=block.hash)
    with pytest.raises(FinalityAttestationError, match="not in the configured"):
        blockchain.submit_validator_finality_attestation(unknown)

    wrong_network = _attestation(validators[0], height=block.index, block_hash=block.hash, network_id="zoidberg-devnet-v1")
    with pytest.raises(FinalityAttestationError, match="network_id"):
        blockchain.submit_validator_finality_attestation(wrong_network)

    wrong_hash = _attestation(validators[0], height=block.index, block_hash="a" * 64)
    with pytest.raises(FinalityAttestationError, match="exact canonical block"):
        blockchain.submit_validator_finality_attestation(wrong_hash)

    wrong_height = _attestation(validators[0], height=block.index + 1, block_hash=block.hash)
    with pytest.raises(FinalityAttestationError, match="nonexistent canonical block"):
        blockchain.submit_validator_finality_attestation(wrong_height)

    bad_signature = _attestation(validators[0], height=block.index, block_hash=block.hash)
    bad_signature["signature"] = "0x00"
    with pytest.raises(FinalityAttestationError, match="signature"):
        blockchain.submit_validator_finality_attestation(bad_signature)

    with pytest.raises(FinalityAttestationError, match="block_height"):
        blockchain.submit_validator_finality_attestation({})


def test_equivocation_is_detected_and_never_counts_for_both_hashes():
    validators = _accounts(3)
    validator_set = [account.address for account in validators]
    service = FinalityService()
    first_block = {"index": 7, "hash": "a" * 64}
    second_block = {"index": 7, "hash": "b" * 64}
    first = _attestation(validators[0], height=7, block_hash=first_block["hash"])
    second = _attestation(validators[0], height=7, block_hash=second_block["hash"])
    result = service.process_attestation(
        first, validator_set=validator_set, expected_network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        canonical_block=first_block, existing_attestations=[], finalized_blocks=[],
    )
    conflict = service.process_attestation(
        second, validator_set=validator_set, expected_network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        canonical_block=second_block, existing_attestations=[result["attestation"]], finalized_blocks=[],
    )
    assert conflict["status"] == "equivocation"
    assert conflict["vote_count"] == 0
    assert conflict["finalization"] is None


def test_finalized_anchor_cannot_be_replaced_by_a_conflicting_chain(blockchain):
    validators = _accounts()
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    block = blockchain.get_latest_block()
    for account in validators[:2]:
        blockchain.submit_validator_finality_attestation(_attestation(account, height=block.index, block_hash=block.hash))
    conflicting = [{"index": 0, "hash": "f" * 64}]
    assert blockchain._candidate_preserves_finalized_blocks(conflicting) is False
