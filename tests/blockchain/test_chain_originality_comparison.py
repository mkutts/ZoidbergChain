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


def _same_height_equal_score_chains(blockchain, wallets):
    first_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    second_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_two"].public_key,
        count=1,
        start_timestamp=1_000_002.0,
    )
    lower_hash_chain, higher_hash_chain = sorted(
        [first_chain, second_chain],
        key=lambda chain: chain[-1].hash,
    )
    assert lower_hash_chain[-1].hash < higher_hash_chain[-1].hash
    return lower_hash_chain, higher_hash_chain


def _select_best_chain(blockchain, chains):
    selected_chain = chains[0]
    for candidate_chain in chains[1:]:
        result = blockchain.compare_chains_by_originality(selected_chain, candidate_chain)
        if result["decision"] == "replace_with_candidate":
            selected_chain = candidate_chain
    return selected_chain


def test_higher_originality_score_chain_wins(
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

    assert result["decision"] == "replace_with_candidate"
    assert result["reason"] == "higher_originality_score"


def test_equal_score_higher_height_wins(blockchain, wallets):
    candidate_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_chain)

    assert result["decision"] == "replace_with_candidate"
    assert result["reason"] == "higher_chain_height"


def test_equal_score_and_height_lower_latest_block_hash_wins(blockchain, wallets):
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(blockchain, wallets)

    result = blockchain.compare_chains_by_originality(higher_hash_chain, lower_hash_chain)

    assert result["decision"] == "replace_with_candidate"
    assert result["reason"] == "lower_latest_block_hash"
    assert result["candidate_latest_hash"] < result["local_latest_hash"]


def test_exact_same_latest_block_hash_is_equivalent(blockchain, wallets):
    local_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )

    result = blockchain.compare_chains_by_originality(local_chain, list(local_chain))

    assert result["decision"] == "equivalent"
    assert result["reason"] == "same_latest_block_hash"


def test_deterministic_result_is_independent_of_peer_order(blockchain, wallets):
    lower_hash_chain, higher_hash_chain = _same_height_equal_score_chains(blockchain, wallets)
    genesis_chain = blockchain.chain

    first_order_winner = _select_best_chain(
        blockchain,
        [genesis_chain, higher_hash_chain, lower_hash_chain],
    )
    second_order_winner = _select_best_chain(
        blockchain,
        [genesis_chain, lower_hash_chain, higher_hash_chain],
    )

    assert first_order_winner[-1].hash == lower_hash_chain[-1].hash
    assert second_order_winner[-1].hash == lower_hash_chain[-1].hash


def test_longer_lower_score_chain_still_loses(blockchain, submission_image, wallets):
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

    assert result["decision"] == "keep_local"
    assert result["reason"] == "lower_originality_score"
    assert len(candidate_chain) > len(local_chain)


def test_shorter_higher_score_chain_still_wins(blockchain, submission_image, wallets):
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

    assert result["decision"] == "replace_with_candidate"
    assert result["reason"] == "higher_originality_score"
    assert len(candidate_chain) < len(local_chain)


def test_invalid_candidate_rejected_even_if_tie_breaker_would_prefer_it(blockchain, wallets):
    candidate_chain = _legacy_chain(
        blockchain.chain,
        wallets["contributor_one"].public_key,
        count=1,
        start_timestamp=1_000_001.0,
    )
    candidate_dicts = [block.to_dict() for block in candidate_chain]
    candidate_dicts[-1]["hash"] = "invalid-hash"

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_dicts)

    assert result["decision"] == "invalid_candidate"
    assert result["reason"] == "candidate_chain_invalid"


def test_different_genesis_hash_is_rejected(blockchain):
    candidate_chain = [blockchain.chain[0].to_dict()]
    candidate_chain[0]["hash"] = "different-genesis"

    result = blockchain.compare_chains_by_originality(blockchain.chain, candidate_chain)

    assert result["decision"] == "invalid_candidate"
    assert result["reason"] == "different_genesis_hash"
