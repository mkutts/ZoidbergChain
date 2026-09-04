from copy import deepcopy

import pytest

from services import (
    FinalityPolicy,
    FinalityService,
    ForkChoiceCollaborators,
    ForkChoiceService,
)


def test_finality_service_derives_canonical_confirmed_and_finalized_states():
    service = FinalityService()
    policy = FinalityPolicy(confirmation_depth=2, finality_depth=6)
    chain = [{"index": index, "hash": f"hash-{index}"} for index in range(7)]

    finalized = service.block_chain_state("hash-0", chain, policy)
    confirmed = service.block_chain_state("hash-4", chain, policy)
    canonical = service.block_chain_state("hash-6", chain, policy)
    absent = service.block_chain_state("other", chain, policy)

    assert (finalized["confirmations"], finalized["phase"], finalized["finalized"]) == (6, "confirmed", False)
    assert (confirmed["confirmations"], confirmed["phase"], confirmed["confirmed"]) == (2, "confirmed", True)
    assert (canonical["confirmations"], canonical["phase"], canonical["confirmed"]) == (0, "canonical", False)
    assert absent["canonical"] is False
    assert absent["confirmations"] is None
    assert finalized["finality_model"] == "validator_quorum"
    assert finalized["finality_scope"] == "known_validator_set"


def test_fork_choice_service_preserves_score_height_and_hash_tie_break_order():
    service = ForkChoiceService()
    collaborators = ForkChoiceCollaborators(lambda chain: list(chain), lambda chain: True)
    genesis = {"index": 0, "hash": "genesis", "originality_score": 999}
    local = [genesis, {"index": 1, "hash": "bbb", "originality_score": 0.75}]

    higher_score = [genesis, {"index": 1, "hash": "zzz", "originality_score": 0.8}]
    higher_height = [genesis, {"index": 1, "hash": "ccc", "originality_score": 0.75}, {"index": 2, "hash": "ddd", "originality_score": 0}]
    lower_hash = [genesis, {"index": 1, "hash": "aaa", "originality_score": 0.75}]

    assert service.compare(local, higher_score, collaborators)["reason"] == "higher_originality_score"
    assert service.compare(local, higher_height, collaborators)["reason"] == "higher_chain_height"
    assert service.compare(local, lower_hash, collaborators)["reason"] == "lower_latest_block_hash"
    assert service.cumulative_originality_score(local) == 0.75


def test_fork_choice_service_rejects_invalid_and_foreign_genesis_candidates():
    service = ForkChoiceService()
    local = [{"index": 0, "hash": "genesis"}]
    invalid = ForkChoiceCollaborators(lambda chain: list(chain), lambda chain: False)

    assert service.compare(local, local, invalid)["reason"] == "candidate_chain_invalid"
    foreign = [{"index": 0, "hash": "foreign"}]
    assert service.compare(local, foreign, invalid)["reason"] == "different_genesis_hash"


def test_production_and_validation_services_build_and_validate_candidate_directly(blockchain, wallets):
    candidate = blockchain._block_production_service.build_candidate(
        blockchain._block_production_state(),
        blockchain._block_production_collaborators(),
        "",
        text_content="Task 9 direct service candidate",
        miner=wallets["owner"].public_key,
        validate_meme=False,
    )

    block = candidate["block"]
    assert candidate["candidate_type"] == "legacy"
    assert block.previous_hash == blockchain.get_latest_block().hash
    assert blockchain._block_validation_service.validate_candidate(
        block,
        blockchain._block_validation_collaborators(),
        current_chain=blockchain.chain,
    ) is True

    tampered_previous = deepcopy(block)
    tampered_previous.previous_hash = "0" * 64
    with pytest.raises(ValueError, match="does not extend"):
        blockchain._block_validation_service.validate_candidate(
            tampered_previous,
            blockchain._block_validation_collaborators(),
            current_chain=blockchain.chain,
        )

    tampered_hash = deepcopy(block)
    tampered_hash.hash = "f" * 64
    with pytest.raises(ValueError, match="does not match block contents"):
        blockchain._block_validation_service.validate_candidate(
            tampered_hash,
            blockchain._block_validation_collaborators(),
            current_chain=blockchain.chain,
        )


def test_consensus_views_are_fresh_after_facade_chain_rebind(blockchain):
    first_production_state = blockchain._block_production_state()
    first_validation = blockchain._block_validation_collaborators()
    rebound_chain = list(blockchain.chain)
    blockchain.chain = rebound_chain

    second_production_state = blockchain._block_production_state()
    second_validation = blockchain._block_validation_collaborators()

    assert first_production_state.chain is not rebound_chain
    assert first_validation.chain is not rebound_chain
    assert second_production_state.chain is rebound_chain
    assert second_validation.chain is rebound_chain
