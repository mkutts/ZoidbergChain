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
NODE_ID = os.getenv("NODE_ID", "zoidberg-local-node").strip()
NODE_HOST = os.getenv("NODE_HOST", "127.0.0.1").strip()
NODE_PORT = int(os.getenv("NODE_PORT", "8000"))
PUBLIC_NODE_URL = os.getenv("PUBLIC_NODE_URL", f"http://{NODE_HOST}:{NODE_PORT}").strip().rstrip("/")
NETWORK_NAME = os.getenv("NETWORK_NAME", "zoidberg-testnet").strip()
