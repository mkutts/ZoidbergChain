from eth_account import Account
from eth_account.messages import encode_defunct

from blockchain import Blockchain
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_finality import (
    build_protocol_v1_finality_attestation,
    build_protocol_v1_finality_attestation_message,
)
from config import PROTOCOL_V1_CONFIRMATION_DEPTH


def _attestation(account, block):
    message = build_protocol_v1_finality_attestation_message(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
    )
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    return build_protocol_v1_finality_attestation(
        validator_address=account.address,
        block_height=block.index,
        block_hash=block.hash,
        network_id=PUBLIC_TESTNET_V1_NETWORK_ID,
        signature=signature,
    )


def test_public_status_distinguishes_accepted_confirmation_and_quorum_finality(blockchain, wallets):
    validators = [Account.create() for _ in range(3)]
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    block = blockchain.get_latest_block()

    status = blockchain.get_block_chain_state(block)
    assert status["canonical"] is True
    assert status["lifecycle_state"] == "accepted"
    assert status["finalized"] is False
    assert status["valid_attestation_count"] == 0
    assert status["validator_set_size"] == 3
    assert status["quorum_required"] == 2

    blockchain.submit_validator_finality_attestation(_attestation(validators[0], block))
    duplicate = blockchain.submit_validator_finality_attestation(_attestation(validators[0], block))
    assert duplicate["status"] == "duplicate"
    assert blockchain.get_block_chain_state(block)["valid_attestation_count"] == 1

    blockchain.submit_validator_finality_attestation(_attestation(validators[1], block))
    status = blockchain.get_block_chain_state(block)
    assert status["lifecycle_state"] == "finalized"
    assert status["finalized"] is True
    assert status["valid_attestation_count"] == status["quorum_required"] == 2
    assert status["finality_evidence"]["attesting_validators"] == list(
        sorted(account.address.lower() for account in validators[:2])
    )
    assert status["finalized_at"] is None
    assert blockchain.get_finalized_head() == {"block_height": block.index, "block_hash": block.hash}


def test_confirmation_depth_does_not_finalize_without_validator_quorum(blockchain, submission_image, wallets):
    validators = [Account.create() for _ in range(3)]
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    target = blockchain.get_latest_block()
    for index in range(PROTOCOL_V1_CONFIRMATION_DEPTH):
        assert blockchain.add_block(
            image_path=str(submission_image),
            text_content=f"Task 3.6 depth filler {index}",
            miner=wallets["owner"].public_key,
            validate_meme=False,
        ) is True

    status = blockchain.get_block_chain_state(target)
    assert status["confirmed"] is True
    assert status["finalized"] is False
    assert status["lifecycle_state"] == "accepted"


def test_public_finality_status_survives_reload(blockchain, wallets):
    validators = [Account.create() for _ in range(3)]
    blockchain.validator_set = tuple(sorted(account.address.lower() for account in validators))
    block = blockchain.get_latest_block()
    for account in validators[:2]:
        blockchain.submit_validator_finality_attestation(_attestation(account, block))

    reloaded = Blockchain(
        wallets["owner"], wallets["contributor_one"], wallets["contributor_two"],
        storage_backend=blockchain.storage, validator_set=blockchain.validator_set,
    )
    status = reloaded.get_block_chain_state(block.hash)
    assert status["finalized"] is True
    assert status["valid_attestation_count"] == 2
    assert reloaded.get_finalized_head() == blockchain.get_finalized_head()
