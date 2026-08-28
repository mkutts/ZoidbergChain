from pathlib import Path

import pytest

from blockchain import Blockchain
from protocol_v1 import PUBLIC_TESTNET_V1_NETWORK_ID, encode_canonical_bytes
from storage import JSONStorageBackend, SQLiteStorageBackend
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from wallet import Wallet


def _json_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return JSONStorageBackend(
        blockchain_file=str(node_dir / "blockchain.json"),
        peers_file=str(node_dir / "peers.json"),
    )


def _sqlite_backend(base_dir, name="node"):
    node_dir = base_dir / name
    return SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))


def _wallets():
    return {
        "owner": Wallet(),
        "contributor_one": Wallet(),
        "contributor_two": Wallet(),
    }


def _certified_submission(blockchain, submission_image, wallets, *, text_content="Protocol v1 certified block"):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text_content,
        submitter=wallets["owner"].public_key,
    )
    for index, vote_type in enumerate(
        [
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_ORIGINAL,
            VOTE_NOT_ORIGINAL,
        ]
    ):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"protocol-v1-voter-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_100,
    )
    certificate = blockchain.get_originality_certificate_for_submission(submission.submission_id)
    blockchain.add_to_mint_queue(submission.submission_id)
    return submission, certificate


def _mint_protocol_v1_block(blockchain, submission_image, wallets, *, text_content="Protocol v1 certified block"):
    submission, certificate = _certified_submission(
        blockchain,
        submission_image,
        wallets,
        text_content=text_content,
    )
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    return submission, certificate, blockchain.get_latest_block()


def test_protocol_v1_minted_block_embeds_media_and_recovers_without_content_cache(
    blockchain,
    submission_image,
    wallets,
):
    submission, _certificate, block = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    original_bytes = Path(submission.image_path).read_bytes()

    assert block.block_version == 1
    assert block.network_id == PUBLIC_TESTNET_V1_NETWORK_ID
    assert block.media_bytes == original_bytes
    assert block.media_hash
    assert block.content_hash == block.media_hash
    assert block.to_dict()["media_bytes"]["$value"]

    content_path = Path(submission.image_path)
    sidecar_path = content_path.with_suffix(content_path.suffix + ".sha256")
    content_path.unlink()
    if sidecar_path.exists():
        sidecar_path.unlink()

    reloaded = Blockchain(storage_backend=blockchain.storage)
    reloaded_block = reloaded.get_latest_block()
    assert reloaded_block.hash == block.hash
    assert reloaded_block.media_bytes == original_bytes
    assert reloaded.recover_block_media_bytes(reloaded_block.hash) == original_bytes


def test_protocol_v1_block_validation_rejects_modified_embedded_media_without_content_cache(
    blockchain,
    submission_image,
    wallets,
):
    submission, _certificate, block = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    content_path = Path(submission.image_path)
    sidecar_path = content_path.with_suffix(content_path.suffix + ".sha256")
    content_path.unlink()
    if sidecar_path.exists():
        sidecar_path.unlink()
    blockchain.content_objects = []

    tampered_media = bytearray(block.media_bytes)
    tampered_media[0] ^= 0x01
    block_dict = block.to_dict()
    block_dict["media_bytes"] = encode_canonical_bytes(bytes(tampered_media))
    block_dict["hash"] = blockchain.calculate_hash_from_dict(block_dict)

    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict(), block_dict]) is False


def test_protocol_v1_block_validation_rejects_modified_declared_media_hash(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    block_dict = block.to_dict()
    block_dict["media_hash"] = "0" * 64
    block_dict["hash"] = blockchain.calculate_hash_from_dict(block_dict)

    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict(), block_dict]) is False


def test_protocol_v1_block_validation_rejects_modified_declared_content_hash(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_protocol_v1_block(blockchain, submission_image, wallets)
    block_dict = block.to_dict()
    block_dict["content_hash"] = "1" * 64
    block_dict["hash"] = blockchain.calculate_hash_from_dict(block_dict)

    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict(), block_dict]) is False


@pytest.mark.parametrize("backend_factory", [_json_backend, _sqlite_backend])
def test_protocol_v1_block_round_trip_preserves_hash_and_media(
    backend_factory,
    isolated_data_dir,
    submission_image,
):
    wallets = _wallets()
    backend = backend_factory(isolated_data_dir, "protocol-v1")
    blockchain = Blockchain(
        project_owner_wallet=wallets["owner"],
        Contributor_one=wallets["contributor_one"],
        Contributor_two=wallets["contributor_two"],
        storage_backend=backend,
    )
    _submission, _certificate, block = _mint_protocol_v1_block(blockchain, submission_image, wallets)

    reloaded = Blockchain(storage_backend=backend)
    reloaded_block = reloaded.get_latest_block()
    assert reloaded_block.block_version == 1
    assert reloaded_block.network_id == PUBLIC_TESTNET_V1_NETWORK_ID
    assert reloaded_block.media_bytes == block.media_bytes
    assert reloaded_block.hash == block.hash
    assert reloaded.calculate_hash_from_dict(reloaded_block.to_dict()) == block.hash


def test_protocol_v1_duplicate_certified_submission_guard_blocks_double_mint(
    blockchain,
    submission_image,
    wallets,
):
    submission, certificate, _block = _mint_protocol_v1_block(blockchain, submission_image, wallets)

    with pytest.raises(ValueError, match="already minted into a block"):
        blockchain.add_block(
            image_path=submission.image_path,
            text_content=submission.text_content,
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
            certificate=certificate,
            reward_recipient=wallets["owner"].public_key,
        )


def test_protocol_v1_mint_rejects_certificate_content_hash_mismatch(
    blockchain,
    submission_image,
    wallets,
):
    submission, certificate = _certified_submission(blockchain, submission_image, wallets)
    certificate.content_hash = "1" * 64

    with pytest.raises(ValueError, match="content_hash does not match canonical media bytes"):
        blockchain.add_block(
            image_path=submission.image_path,
            text_content=submission.text_content,
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
            certificate=certificate,
            reward_recipient=wallets["owner"].public_key,
        )
