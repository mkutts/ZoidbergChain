COIN_NAME = "ZoidbergCoin"
TICKER = "ZOID"
TOTAL_SUPPLY = 1_000_000_000
REWARD_POOL_SUPPLY = 100_000_000
MEME_BLOCK_REWARD = 5
VOTING_WINDOW_HOURS = 24
MIN_VOTE_FLOOR = 5
ACTIVE_USER_PERCENT_FOR_MIN_VOTES = 0.05
ORIGINALITY_APPROVAL_THRESHOLD = 0.70
ACTIVE_USER_LOOKBACK_DAYS = 7

import os


def _env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
RATE_LIMIT_ENABLED = _env_flag("RATE_LIMIT_ENABLED", APP_ENV == "production")
TRANSACTION_RATE_LIMIT = os.getenv("TRANSACTION_RATE_LIMIT", "5/minute")
SUBMISSION_RATE_LIMIT = os.getenv("SUBMISSION_RATE_LIMIT", "5/minute")
VOTE_RATE_LIMIT = os.getenv("VOTE_RATE_LIMIT", "10/minute")
ADD_BLOCK_RATE_LIMIT = os.getenv("ADD_BLOCK_RATE_LIMIT", "3/minute")
WALLET_GENERATION_RATE_LIMIT = os.getenv("WALLET_GENERATION_RATE_LIMIT", "2/minute")
