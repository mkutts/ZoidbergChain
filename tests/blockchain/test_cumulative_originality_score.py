from block import Block
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from transaction import Transaction


def _certified_submission(blockchain, submission_image, submitter, text, voter_prefix):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
        submitter=submitter,
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
            voter=f"{voter_prefix}-{index}",
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


def _mint_certified_block(blockchain, submission_image, wallets, text, voter_prefix):
    _submission, certificate = _certified_submission(
        blockchain,
        submission_image,
        wallets["owner"].public_key,
        text,
        voter_prefix,
    )
    assert blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    ) is True
    return certificate, blockchain.get_latest_block()


def _legacy_block(blockchain, miner, timestamp=1_000_000):
    latest_block = blockchain.get_latest_block()
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=timestamp,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=timestamp)],
        miner=miner,
        meme={"encoded_image": "legacy-image", "text": "Legacy block"},
    )


def test_genesis_only_chain_has_zero_cumulative_originality_score(blockchain):
    assert blockchain.get_cumulative_originality_score() == 0
    assert blockchain.calculate_cumulative_originality_score(blockchain.chain) == 0


def test_one_certified_meme_block_returns_block_originality_score(
    blockchain,
    submission_image,
    wallets,
):
    _certificate, block = _mint_certified_block(
        blockchain,
        submission_image,
        wallets,
        "First scored meme",
        "score-voter-one",
    )

    assert blockchain.get_cumulative_originality_score() == block.originality_score


def test_multiple_certified_meme_blocks_sum_correctly(blockchain, submission_image, wallets):
    _first_certificate, first_block = _mint_certified_block(
        blockchain,
        submission_image,
        wallets,
        "First cumulative meme",
        "score-voter-first",
    )
    _second_certificate, second_block = _mint_certified_block(
        blockchain,
        submission_image,
        wallets,
        "Second cumulative meme",
        "score-voter-second",
    )

    expected_score = round(first_block.originality_score + second_block.originality_score, 8)

    assert blockchain.get_cumulative_originality_score() == expected_score


def test_non_certified_blocks_do_not_inflate_score(blockchain, wallets):
    blockchain.chain.append(_legacy_block(blockchain, wallets["contributor_one"].public_key))

    assert blockchain.get_cumulative_originality_score() == 0


def test_missing_originality_score_on_legacy_block_contributes_zero(blockchain, wallets):
    legacy_block = _legacy_block(blockchain, wallets["contributor_one"].public_key)
    legacy_block.originality_score = None
    blockchain.chain.append(legacy_block)

    assert blockchain.get_cumulative_originality_score() == 0


def test_cumulative_originality_score_is_deterministic(
    blockchain,
    submission_image,
    wallets,
):
    _mint_certified_block(
        blockchain,
        submission_image,
        wallets,
        "Deterministic score meme",
        "score-voter-deterministic",
    )

    first_score = blockchain.get_cumulative_originality_score()
    second_score = blockchain.get_cumulative_originality_score()

    assert first_score == second_score
