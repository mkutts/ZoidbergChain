import os


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
BASE_ORIGINALITY_SCORE = 1.0
DECISIVE_VOTE_WEIGHT = 0.10
APPROVAL_PERCENTAGE_WEIGHT = 1.0
UNSURE_VOTE_WEIGHT = 0.0

VALID_ENVIRONMENTS = {"development", "testnet", "production"}

_SECURITY_DEFAULTS = {
    "development": {
        "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT": True,
        "ALLOW_DEV_RESET_ENDPOINTS": True,
        "ALLOW_INSECURE_LOCAL_PEERS": True,
        "ENABLE_RATE_LIMITING": False,
        "ENABLE_SIGNED_PEER_MESSAGES": False,
        "PEER_REPLAY_PROTECTION_ENABLED": False,
        "REQUIRE_PEER_AUTH": False,
        "PUBLIC_API_MODE": False,
    },
    "testnet": {
        "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT": False,
        "ALLOW_DEV_RESET_ENDPOINTS": False,
        "ALLOW_INSECURE_LOCAL_PEERS": False,
        "ENABLE_RATE_LIMITING": True,
        "ENABLE_SIGNED_PEER_MESSAGES": True,
        "PEER_REPLAY_PROTECTION_ENABLED": True,
        "REQUIRE_PEER_AUTH": True,
        "PUBLIC_API_MODE": True,
    },
    "production": {
        "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT": False,
        "ALLOW_DEV_RESET_ENDPOINTS": False,
        "ALLOW_INSECURE_LOCAL_PEERS": False,
        "ENABLE_RATE_LIMITING": True,
        "ENABLE_SIGNED_PEER_MESSAGES": True,
        "PEER_REPLAY_PROTECTION_ENABLED": True,
        "REQUIRE_PEER_AUTH": True,
        "PUBLIC_API_MODE": True,
    },
}


def _clean_path(value):
    cleaned = (value or ".").strip()
    return cleaned or "."


def build_data_paths(data_dir):
    data_dir = _clean_path(data_dir)
    temp_dir = os.path.join(data_dir, "temp")
    return {
        "data_dir": data_dir,
        "blockchain_file": os.path.join(data_dir, "blockchain.json"),
        "peers_file": os.path.join(data_dir, "peers.json"),
        "temp_dir": temp_dir,
        "submissions_dir": os.path.join(temp_dir, "submissions"),
    }


def _env_flag(name, default=False):
    return _env_flag_any((name,), default)


def _env_flag_any(names, default=False):
    for name in names:
        value = os.getenv(name)
        if value is not None:
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError(
                f"Invalid boolean value for {name}: {value!r}. "
                "Use true/false, yes/no, on/off, or 1/0."
            )
    return default


def _env_int(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except (AttributeError, ValueError):
        raise ValueError(f"Invalid integer value for {name}: {value!r}.")


def _load_environment():
    raw_environment = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development"))
    environment = (raw_environment or "development").strip().lower()
    if environment not in VALID_ENVIRONMENTS:
        valid_values = ", ".join(sorted(VALID_ENVIRONMENTS))
        raise ValueError(
            f"Invalid ENVIRONMENT value: {raw_environment!r}. "
            f"Expected one of: {valid_values}."
        )
    return environment


ENVIRONMENT = _load_environment()
APP_ENV = ENVIRONMENT
_CURRENT_SECURITY_DEFAULTS = _SECURITY_DEFAULTS[ENVIRONMENT]

ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT = _env_flag(
    "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT",
    _CURRENT_SECURITY_DEFAULTS["ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT"],
)
ALLOW_DEV_RESET_ENDPOINTS = _env_flag(
    "ALLOW_DEV_RESET_ENDPOINTS",
    _CURRENT_SECURITY_DEFAULTS["ALLOW_DEV_RESET_ENDPOINTS"],
)
ALLOW_INSECURE_LOCAL_PEERS = _env_flag(
    "ALLOW_INSECURE_LOCAL_PEERS",
    _CURRENT_SECURITY_DEFAULTS["ALLOW_INSECURE_LOCAL_PEERS"],
)
ENABLE_RATE_LIMITING = _env_flag_any(
    ("ENABLE_RATE_LIMITING", "RATE_LIMIT_ENABLED"),
    _CURRENT_SECURITY_DEFAULTS["ENABLE_RATE_LIMITING"],
)
ENABLE_SIGNED_PEER_MESSAGES = _env_flag(
    "ENABLE_SIGNED_PEER_MESSAGES",
    _CURRENT_SECURITY_DEFAULTS["ENABLE_SIGNED_PEER_MESSAGES"],
)
PEER_SIGNATURE_WINDOW_SECONDS = _env_int("PEER_SIGNATURE_WINDOW_SECONDS", 300)
PEER_REPLAY_PROTECTION_ENABLED = _env_flag(
    "PEER_REPLAY_PROTECTION_ENABLED",
    _CURRENT_SECURITY_DEFAULTS["PEER_REPLAY_PROTECTION_ENABLED"],
)
REQUIRE_PEER_AUTH = _env_flag(
    "REQUIRE_PEER_AUTH",
    _CURRENT_SECURITY_DEFAULTS["REQUIRE_PEER_AUTH"],
)
PUBLIC_API_MODE = _env_flag(
    "PUBLIC_API_MODE",
    _CURRENT_SECURITY_DEFAULTS["PUBLIC_API_MODE"],
)

# Backward-compatible alias for existing imports and older local scripts.
RATE_LIMIT_ENABLED = ENABLE_RATE_LIMITING


def is_development():
    return ENVIRONMENT == "development"


def is_testnet():
    return ENVIRONMENT == "testnet"


def is_production():
    return ENVIRONMENT == "production"


def allow_private_key_export():
    return ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT


def allow_dev_reset_endpoints():
    return ALLOW_DEV_RESET_ENDPOINTS


def allow_insecure_local_peers():
    return ALLOW_INSECURE_LOCAL_PEERS


def rate_limiting_enabled():
    return ENABLE_RATE_LIMITING


def signed_peer_messages_enabled():
    return ENABLE_SIGNED_PEER_MESSAGES


def peer_signature_window_seconds():
    return PEER_SIGNATURE_WINDOW_SECONDS


def peer_replay_protection_enabled():
    return PEER_REPLAY_PROTECTION_ENABLED


def require_peer_auth():
    return REQUIRE_PEER_AUTH


def public_api_mode_enabled():
    return PUBLIC_API_MODE


def peer_auth_required():
    return REQUIRE_PEER_AUTH


def peer_shared_secret():
    return _env_value("PEER_SHARED_SECRET", "")


def peer_shared_secret_is_configured():
    secret = peer_shared_secret()
    return bool(secret) and secret.lower() not in {
        "change-me",
        "replace-with-long-random-secret",
    }


def validate_peer_auth_config():
    if (REQUIRE_PEER_AUTH or ENABLE_SIGNED_PEER_MESSAGES) and not peer_shared_secret_is_configured():
        raise ValueError(
            "PEER_SHARED_SECRET must be set to a non-default value when peer auth or signed peer messages are enabled."
        )


def _env_value(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


TRANSACTION_RATE_LIMIT = os.getenv("TRANSACTION_RATE_LIMIT", "5/minute")
SUBMISSION_RATE_LIMIT = os.getenv("SUBMISSION_RATE_LIMIT", "5/minute")
VOTE_RATE_LIMIT = os.getenv("VOTE_RATE_LIMIT", "10/minute")
ADD_BLOCK_RATE_LIMIT = os.getenv("ADD_BLOCK_RATE_LIMIT", "3/minute")
WALLET_GENERATION_RATE_LIMIT = os.getenv("WALLET_GENERATION_RATE_LIMIT", "2/minute")
NODE_ID = _env_value("NODE_ID", "zoidberg-local-node")
NODE_HOST = _env_value("NODE_HOST", "127.0.0.1")
NODE_PORT = int(os.getenv("NODE_PORT", "8000"))
PUBLIC_NODE_URL = _env_value("PUBLIC_NODE_URL", f"http://{NODE_HOST}:{NODE_PORT}").rstrip("/")
NETWORK_NAME = _env_value("NETWORK_NAME", "zoidberg-testnet")
NODE_DATA_DIR = _clean_path(os.getenv("NODE_DATA_DIR", os.getenv("DATA_DIR", ".")))
DATA_DIR = NODE_DATA_DIR
_DATA_PATHS = build_data_paths(DATA_DIR)
BLOCKCHAIN_FILE = _DATA_PATHS["blockchain_file"]
PEERS_FILE = _DATA_PATHS["peers_file"]
TEMP_DIR = _DATA_PATHS["temp_dir"]
SUBMISSIONS_DIR = _DATA_PATHS["submissions_dir"]

validate_peer_auth_config()
