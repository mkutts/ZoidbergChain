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
VALID_STORAGE_BACKENDS = {"json"}

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

_RATE_LIMIT_DEFAULTS = {
    "development": {
        "RATE_LIMIT_TRANSACTION_CREATE": "30/minute",
        "RATE_LIMIT_WALLET_CREATE": "30/minute",
        "RATE_LIMIT_SUBMISSION_CREATE": "20/minute",
        "RATE_LIMIT_VOTE": "60/minute",
        "RATE_LIMIT_EVALUATE": "20/minute",
        "RATE_LIMIT_MINT": "20/minute",
        "RATE_LIMIT_CHAIN_SYNC": "30/minute",
        "RATE_LIMIT_PEER_RECEIVE": "120/minute",
        "RATE_LIMIT_PUBLIC_READ": "120/minute",
        "RATE_LIMIT_DEV_ENDPOINTS": "30/minute",
    },
    "testnet": {
        "RATE_LIMIT_TRANSACTION_CREATE": "10/minute",
        "RATE_LIMIT_WALLET_CREATE": "10/minute",
        "RATE_LIMIT_SUBMISSION_CREATE": "10/minute",
        "RATE_LIMIT_VOTE": "30/minute",
        "RATE_LIMIT_EVALUATE": "10/minute",
        "RATE_LIMIT_MINT": "10/minute",
        "RATE_LIMIT_CHAIN_SYNC": "20/minute",
        "RATE_LIMIT_PEER_RECEIVE": "120/minute",
        "RATE_LIMIT_PUBLIC_READ": "180/minute",
        "RATE_LIMIT_DEV_ENDPOINTS": "5/minute",
    },
    "production": {
        "RATE_LIMIT_TRANSACTION_CREATE": "10/minute",
        "RATE_LIMIT_WALLET_CREATE": "10/minute",
        "RATE_LIMIT_SUBMISSION_CREATE": "10/minute",
        "RATE_LIMIT_VOTE": "30/minute",
        "RATE_LIMIT_EVALUATE": "10/minute",
        "RATE_LIMIT_MINT": "10/minute",
        "RATE_LIMIT_CHAIN_SYNC": "20/minute",
        "RATE_LIMIT_PEER_RECEIVE": "120/minute",
        "RATE_LIMIT_PUBLIC_READ": "180/minute",
        "RATE_LIMIT_DEV_ENDPOINTS": "5/minute",
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


def _env_value_any(names, default):
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value.strip()
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
_CURRENT_RATE_LIMIT_DEFAULTS = _RATE_LIMIT_DEFAULTS[ENVIRONMENT]

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


def get_rate_limit(name):
    try:
        return RATE_LIMITS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown rate limit category: {name!r}.") from exc


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


RATE_LIMIT_TRANSACTION_CREATE = _env_value_any(
    ("RATE_LIMIT_TRANSACTION_CREATE", "TRANSACTION_RATE_LIMIT"),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_TRANSACTION_CREATE"],
)
RATE_LIMIT_WALLET_CREATE = _env_value_any(
    ("RATE_LIMIT_WALLET_CREATE", "WALLET_GENERATION_RATE_LIMIT"),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_WALLET_CREATE"],
)
RATE_LIMIT_SUBMISSION_CREATE = _env_value_any(
    ("RATE_LIMIT_SUBMISSION_CREATE", "SUBMISSION_RATE_LIMIT"),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_SUBMISSION_CREATE"],
)
RATE_LIMIT_VOTE = _env_value_any(
    ("RATE_LIMIT_VOTE", "VOTE_RATE_LIMIT"),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_VOTE"],
)
RATE_LIMIT_EVALUATE = _env_value_any(
    ("RATE_LIMIT_EVALUATE",),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_EVALUATE"],
)
RATE_LIMIT_MINT = _env_value_any(
    ("RATE_LIMIT_MINT", "ADD_BLOCK_RATE_LIMIT"),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_MINT"],
)
RATE_LIMIT_CHAIN_SYNC = _env_value_any(
    ("RATE_LIMIT_CHAIN_SYNC",),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_CHAIN_SYNC"],
)
RATE_LIMIT_PEER_RECEIVE = _env_value_any(
    ("RATE_LIMIT_PEER_RECEIVE",),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_PEER_RECEIVE"],
)
RATE_LIMIT_PUBLIC_READ = _env_value_any(
    ("RATE_LIMIT_PUBLIC_READ",),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_PUBLIC_READ"],
)
RATE_LIMIT_DEV_ENDPOINTS = _env_value_any(
    ("RATE_LIMIT_DEV_ENDPOINTS",),
    _CURRENT_RATE_LIMIT_DEFAULTS["RATE_LIMIT_DEV_ENDPOINTS"],
)

RATE_LIMITS = {
    "transaction_create": RATE_LIMIT_TRANSACTION_CREATE,
    "wallet_create": RATE_LIMIT_WALLET_CREATE,
    "submission_create": RATE_LIMIT_SUBMISSION_CREATE,
    "vote": RATE_LIMIT_VOTE,
    "evaluate": RATE_LIMIT_EVALUATE,
    "mint": RATE_LIMIT_MINT,
    "chain_sync": RATE_LIMIT_CHAIN_SYNC,
    "peer_receive": RATE_LIMIT_PEER_RECEIVE,
    "public_read": RATE_LIMIT_PUBLIC_READ,
    "dev_endpoint": RATE_LIMIT_DEV_ENDPOINTS,
}

TRANSACTION_RATE_LIMIT = RATE_LIMIT_TRANSACTION_CREATE
WALLET_GENERATION_RATE_LIMIT = RATE_LIMIT_WALLET_CREATE
SUBMISSION_RATE_LIMIT = RATE_LIMIT_SUBMISSION_CREATE
VOTE_RATE_LIMIT = RATE_LIMIT_VOTE
ADD_BLOCK_RATE_LIMIT = RATE_LIMIT_MINT
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
STORAGE_BACKEND = _env_value("STORAGE_BACKEND", "json").strip().lower()
if STORAGE_BACKEND not in VALID_STORAGE_BACKENDS:
    supported_backends = ", ".join(sorted(VALID_STORAGE_BACKENDS))
    raise ValueError(
        f"Invalid STORAGE_BACKEND value: {STORAGE_BACKEND!r}. "
        f"Expected one of: {supported_backends}."
    )

validate_peer_auth_config()
