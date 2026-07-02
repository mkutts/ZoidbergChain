from block import Block
from submission import VOTE_NOT_ORIGINAL, VOTE_ORIGINAL
from transaction import Transaction


def _next_block(chain, miner, timestamp=1_000_000.0, text="Legacy comparison block"):
    latest_block = chain[-1]
    return Block(
        index=latest_block.index + 1,
        previous_hash=latest_block.hash,
        timestamp=timestamp,
        transactions=[Transaction("REWARD_POOL", miner, 5, created_at=timestamp)],
        miner=miner,
        meme={"encoded_image": "legacy-image", "text": text},
    )


def _legacy_chain(base_chain, miner, count, start_timestamp=1_000_000.0):
    chain = list(base_chain)
    for offset in range(count):
        chain.append(
            _next_block(
                chain,
                miner,
                timestamp=start_timestamp + offset,
                text=f"Legacy comparison block {offset}",
            )
        )
    return chain


def _mint_certified_block(blockchain, submission_image, wallets, text, voter_prefix):
    submission = blockchain.submit_content(
        image_path=str(submission_image),
        text_content=text,
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
            voter=f"{voter_prefix}-{index}",
            vote_type=vote_type,
            created_at=1_000_000 + index,
        )
    blockchain.evaluate_submission(
        submission.submission_id,
        automated_originality_passed=True,
        now=1_000_100,
    )
    blockchain.add_to_mint_queue(submission.submission_id)
    blockchain.mint_next_queued_submission(
        miner=wallets["contributor_one"].public_key,
        validate_meme=False,
    )
    return blockchain.get_latest_block()


def _certified_chain_from_base(blockchain, base_chain, submission_image, wallets, text, voter_prefix):
    saved_chain = list(blockchain.chain)
    blockchain.chain = list(base_chain)
    block = _mint_certified_block(blockchain, submission_image, wallets, text, voter_prefix)
    certified_chain = list(blockchain.chain)
    blockchain.chain = saved_chain
    return certified_chain, block


def test_higher_originality_score_chain_is_preferred(
    blockchain,
    submission_image,
    wallets,
):
    candidate_chain, _candidate_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Higher score candidate",
        "higher-score-voter",
    )

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_chain)

    assert result["preferred"] == "candidate"
    assert result["reason"] == "higher_originality_score"


def test_longer_lower_score_chain_is_rejected(blockchain, submission_image, wallets):
    local_chain, _local_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Local scored chain",
        "local-scored-voter",
    )
    candidate_chain = _legacy_chain(
        local_chain[:1],
        wallets["contributor_two"].public_key,
        count=3,
        start_timestamp=1_000_300.0,
    )

    result = blockchain.compare_chains_by_originality(local_chain, candidate_chain)

    assert result["preferred"] == "local"
    assert result["reason"] == "lower_originality_score"
    assert len(candidate_chain) > len(local_chain)


def test_shorter_higher_score_chain_is_preferred(blockchain, submission_image, wallets):
    local_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=3,
        start_timestamp=1_000_200.0,
    )
    candidate_chain, _candidate_block = _certified_chain_from_base(
        blockchain,
        local_chain[:1],
        submission_image,
        wallets,
        "Shorter higher score candidate",
        "shorter-higher-voter",
    )

    result = blockchain.compare_chains_by_originality(local_chain, candidate_chain)

    assert result["preferred"] == "candidate"
    assert result["reason"] == "higher_originality_score"
    assert len(candidate_chain) < len(local_chain)


def test_different_genesis_hash_is_rejected(blockchain):
    candidate_chain = [blockchain.chain[0].to_dict()]
    candidate_chain[0]["hash"] = "different-genesis"

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_chain)

    assert result["preferred"] == "local"
    assert result["reason"] == "different_genesis_hash"


def test_invalid_higher_score_chain_is_rejected(
    blockchain,
    submission_image,
    wallets,
):
    candidate_chain, _candidate_block = _certified_chain_from_base(
        blockchain,
        blockchain.chain,
        submission_image,
        wallets,
        "Invalid higher score candidate",
        "invalid-candidate-voter",
    )
    candidate_dicts = [block.to_dict() for block in candidate_chain]
    candidate_dicts[-1]["hash"] = "invalid-hash"

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_dicts)

    assert result["preferred"] == "local"
    assert result["reason"] == "candidate_chain_invalid"


def test_equal_score_fork_is_unresolved(blockchain, wallets):
    local_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    candidate_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_two"].public_key,
        count=1,
        start_timestamp=1_000_002.0,
    )

    result = blockchain.compare_chains_by_originality(local_chain, candidate_chain)

    assert result["preferred"] == "tie"
    assert result["reason"] == "equal_originality_score_unresolved"
