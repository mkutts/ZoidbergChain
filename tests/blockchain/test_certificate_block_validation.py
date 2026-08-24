import pytest

import blockchain as blockchain_module
from pathlib import Path

from originality_certificate import OriginalityCertificate, calculate_originality_score
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL


def _certified_submission(blockchain, submission_image, wallets):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content="Certificate-backed block",
        submitter=wallets["owner"].public_key,
    )
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"block-validation-voter-{index}",
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


def _mint_certificate_backed_block(blockchain, submission_image, wallets):
    submission, certificate = _certified_submission(blockchain, submission_image, wallets)
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    return submission, certificate, blockchain.get_latest_block()


def _rehash(blockchain, block_dict):
    block_dict["hash"] = blockchain.calculate_hash_from_dict(block_dict)
    return block_dict


def _pad_block_to_serialized_size(blockchain, block_dict, target_size):
    block_dict.setdefault("meme", {})
    block_dict["meme"]["padding"] = ""
    _rehash(blockchain, block_dict)
    current_size = blockchain.serialized_block_size_bytes(block_dict)
    if current_size > target_size:
        raise AssertionError(f"Block is already larger than target size {target_size}.")
    block_dict["meme"]["padding"] = "x" * (target_size - current_size)
    _rehash(blockchain, block_dict)
    return block_dict


def test_block_validation_accepts_valid_certificate_backed_block(
    blockchain,
    submission_image,
    wallets,
):
    _submission, certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )

    assert block.originality_score == certificate.originality_score
    assert block.originality_score == calculate_originality_score(certificate)
    assert blockchain.is_chain_valid([block.to_dict() for block in blockchain.chain]) is True


def test_block_validation_rejects_missing_certificate_id(blockchain, submission_image, wallets):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict.pop("certificate_id")

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_unknown_certificate_id(blockchain, submission_image, wallets):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["certificate_id"] = "unknown-certificate"

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_certificate_submission_mismatch(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["submission_id"] = "different-submission"

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_certificate_content_hash_mismatch(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["content_hash"] = "different-content-hash"

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_certificate_content_id_mismatch(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["content_id"] = "0" * 32

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_wrong_network_certificate(
    blockchain,
    submission_image,
    wallets,
):
    _submission, certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    certificate.network_name = "wrong-network"

    assert blockchain.is_chain_valid([block.to_dict() for block in blockchain.chain]) is False


def test_block_validation_rejects_missing_originality_score(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict.pop("originality_score")

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_validation_rejects_mismatched_originality_score(
    blockchain,
    submission_image,
    wallets,
):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["originality_score"] = block_dict["originality_score"] + 1

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_genesis_block_validates_without_certificate(blockchain):
    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict()]) is True


def test_validate_certificate_for_submission_rejects_wrong_network(
    blockchain,
    submission_image,
    wallets,
):
    submission, certificate = _certified_submission(blockchain, submission_image, wallets)
    wrong_network_certificate = OriginalityCertificate.from_dict({
        **certificate.to_dict(),
        "certificate_id": "",
        "network_name": "wrong-network",
    })

    try:
        blockchain.originality_certificates = [wrong_network_certificate]
        blockchain.require_valid_certificate_for_submission(submission)
    except ValueError as error:
        assert str(error) == "Originality certificate belongs to a different network."
    else:
        raise AssertionError("Expected wrong-network certificate to fail validation.")


def test_minted_block_contains_meme_payload_and_content_identifiers(
    blockchain,
    submission_image,
    wallets,
):
    submission, certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )

    block_dict = block.to_dict()

    assert isinstance(block_dict["meme"], dict)
    assert block_dict["meme"]["encoded_content"]
    assert block_dict["meme"]["text"] == submission.text_content
    assert block_dict["submission_id"] == submission.submission_id
    assert block_dict["certificate_id"] == certificate.certificate_id
    assert block_dict["content_hash"] != submission.content_hash
    assert block_dict["original_content_hash"] == submission.content_hash
    assert block_dict["content_id"] == submission.content_id
    assert block_dict["canonical_size_bytes"] <= blockchain_module.MAX_CANONICAL_CONTENT_BYTES
    assert block_dict["compression_algorithm"] == "gzip"


def test_chain_validation_rejects_tampered_verified_uploaded_content_payload(
    blockchain,
    submission_image,
    wallets,
):
    image_bytes = Path(submission_image).read_bytes()
    content_object = blockchain.upload_binary_content(
        file_bytes=image_bytes,
        submitted_by=wallets["owner"].public_key,
        mime_type="image/jpeg",
        original_filename="verified-upload.jpg",
        caption="Verified upload validation path",
    )
    submission = blockchain.submit_existing_content(
        content_hash=content_object.content_hash,
        content_id=content_object.content_id,
        submitter=wallets["owner"].public_key,
        text_content="Verified upload validation path",
    )
    for index, vote_type in enumerate([
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_ORIGINAL,
        VOTE_NOT_ORIGINAL,
    ]):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"verified-content-voter-{index}",
            vote_type=vote_type,
            created_at=1_001_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_001_100,
    )
    blockchain.add_to_mint_queue(submission.submission_id)

    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    block = blockchain.get_latest_block()
    assert blockchain.is_chain_valid([block.to_dict() for block in blockchain.chain]) is True

    stored_content = blockchain.get_content_object_by_hash(content_object.content_hash)
    tampered_path = Path(blockchain.storage.data_dir) / Path(stored_content.local_path)
    tampered_path.write_bytes(b"tampered-content")

    assert blockchain.is_chain_valid([block.to_dict() for block in blockchain.chain]) is False


def test_chain_validation_rejects_tampered_embedded_content(blockchain, submission_image, wallets):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = block.to_dict()
    block_dict["meme"]["encoded_content"] = block_dict["meme"]["encoded_content"][:-4] + "AAAA"

    chain = [blockchain.chain[0].to_dict(), _rehash(blockchain, block_dict)]

    assert blockchain.is_chain_valid(chain) is False


def test_block_exactly_at_max_serialized_size_can_validate(blockchain, submission_image, wallets):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = _pad_block_to_serialized_size(
        blockchain,
        block.to_dict(),
        blockchain_module.MAX_BLOCK_SIZE_BYTES,
    )

    assert blockchain.serialized_block_size_bytes(block_dict) == blockchain_module.MAX_BLOCK_SIZE_BYTES
    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict(), block_dict]) is True


def test_block_over_max_serialized_size_is_rejected(blockchain, submission_image, wallets):
    _submission, _certificate, block = _mint_certificate_backed_block(
        blockchain,
        submission_image,
        wallets,
    )
    block_dict = _pad_block_to_serialized_size(
        blockchain,
        block.to_dict(),
        blockchain_module.MAX_BLOCK_SIZE_BYTES + 1,
    )

    assert blockchain.serialized_block_size_bytes(block_dict) == blockchain_module.MAX_BLOCK_SIZE_BYTES + 1
    assert blockchain.is_chain_valid([blockchain.chain[0].to_dict(), block_dict]) is False


def test_canonical_content_over_max_is_rejected(blockchain, wallets, monkeypatch):
    monkeypatch.setattr(blockchain_module, "MAX_CANONICAL_CONTENT_BYTES", 64)
    image_bytes = bytes(range(256)) * 4
    content_object = blockchain.upload_binary_content(
        file_bytes=image_bytes,
        submitted_by=wallets["owner"].public_key,
        mime_type="image/jpeg",
        original_filename="oversized-canonical.jpg",
        caption="oversized canonical content",
    )
    submission = blockchain.submit_existing_content(
        content_hash=content_object.content_hash,
        content_id=content_object.content_id,
        submitter=wallets["owner"].public_key,
        text_content="oversized canonical content",
    )
    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"oversized-canonical-voter-{index}",
            vote_type=VOTE_ORIGINAL if index < 4 else VOTE_NOT_ORIGINAL,
            created_at=1_002_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_002_100,
    )
    blockchain.add_to_mint_queue(submission.submission_id)

    with pytest.raises(ValueError, match="MAX_CANONICAL_CONTENT_BYTES"):
        blockchain.mint_next_queued_submission(
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
        )


def test_final_serialized_block_over_max_is_rejected_even_if_canonical_content_passes(
    blockchain,
    wallets,
    monkeypatch,
):
    monkeypatch.setattr(blockchain_module, "MAX_BLOCK_SIZE_BYTES", 1_000_000)
    import content

    monkeypatch.setattr(content.config, "MAX_TEXT_CONTENT_BYTES", 1_200_000)
    large_text = "A" * 999_000
    content_object = blockchain.upload_text_content(
        text_content=large_text,
        submitted_by=wallets["owner"].public_key,
        caption="large-text",
    )
    submission = blockchain.submit_existing_content(
        content_hash=content_object.content_hash,
        content_id=content_object.content_id,
        submitter=wallets["owner"].public_key,
        text_content=large_text,
    )
    for index in range(5):
        blockchain.cast_submission_vote(
            submission_id=submission.submission_id,
            voter=f"oversized-block-voter-{index}",
            vote_type=VOTE_ORIGINAL if index < 4 else VOTE_NOT_ORIGINAL,
            created_at=1_003_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_003_100,
    )
    blockchain.add_to_mint_queue(submission.submission_id)

    with pytest.raises(ValueError, match="MAX_BLOCK_SIZE_BYTES"):
        blockchain.mint_next_queued_submission(
            miner=wallets["contributor_one"].public_key,
            validate_meme=False,
        )
