from config import (
    ACTIVE_USER_LOOKBACK_DAYS,
    ACTIVE_USER_PERCENT_FOR_MIN_VOTES,
    APPROVAL_PERCENTAGE_WEIGHT,
    BASE_ORIGINALITY_SCORE,
    COIN_NAME,
    DECISIVE_VOTE_WEIGHT,
    MEME_BLOCK_REWARD,
    MIN_VOTE_FLOOR,
    ORIGINALITY_APPROVAL_THRESHOLD,
    REWARD_POOL_SUPPLY,
    TICKER,
    TOTAL_SUPPLY,
    UNSURE_VOTE_WEIGHT,
    VOTING_WINDOW_HOURS,
)


def test_coin_name():
    assert COIN_NAME == "ZoidbergCoin"


def test_ticker():
    assert TICKER == "ZOID"


def test_total_supply():
    assert TOTAL_SUPPLY == 1_000_000_000


def test_reward_pool():
    assert REWARD_POOL_SUPPLY == 100_000_000


def test_meme_reward():
    assert MEME_BLOCK_REWARD == 5


def test_voting_window():
    assert VOTING_WINDOW_HOURS == 24


def test_vote_floor():
    assert MIN_VOTE_FLOOR == 5
    assert ACTIVE_USER_PERCENT_FOR_MIN_VOTES == 0.05


def test_approval_threshold():
    assert ORIGINALITY_APPROVAL_THRESHOLD == 0.70


def test_active_user_lookback():
    assert ACTIVE_USER_LOOKBACK_DAYS == 7


def test_originality_scoring_weights():
    assert BASE_ORIGINALITY_SCORE == 1.0
    assert DECISIVE_VOTE_WEIGHT == 0.10
    assert APPROVAL_PERCENTAGE_WEIGHT == 1.0
    assert UNSURE_VOTE_WEIGHT == 0.0
