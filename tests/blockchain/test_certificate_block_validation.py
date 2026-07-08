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
    _submission, certificate, _block = _mint_certificate_backed_block(
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
