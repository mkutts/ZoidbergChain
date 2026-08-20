import os
from decimal import Decimal, InvalidOperation


COIN_NAME = "ZoidbergCoin"
TICKER = "ZOID"
TOTAL_SUPPLY = 1_000_000_000
REWARD_POOL_SUPPLY = 100_000_000
MEME_BLOCK_REWARD = 5
MAX_TRANSACTIONS_PER_BLOCK = 10
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
VALID_STORAGE_BACKENDS = {"json", "sqlite"}
DEFAULT_PUBLIC_DEMO_ORIGINS = (
    "https://zoidbergcoin.com",
    "https://www.zoidbergcoin.com",
)
DEFAULT_DEVELOPMENT_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)

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

_VOTER_REWARD_DEFAULTS = {
    "development": {
        "VOTER_REWARDS_ENABLED": False,
        "VOTER_REWARD_POOL_PER_DECISION_ZOID": "1",
        "VOTER_REWARD_MAX_PER_WALLET_ZOID": "0",
        "VOTER_REWARD_MIN_DECISIVE_VOTES": 1,
        "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE": True,
        "VOTER_REWARD_APPROVAL_SIDE": "original",
        "VOTER_REWARD_REJECTION_SIDE": "not_original",
    },
    "testnet": {
        "VOTER_REWARDS_ENABLED": False,
        "VOTER_REWARD_POOL_PER_DECISION_ZOID": "1",
        "VOTER_REWARD_MAX_PER_WALLET_ZOID": "0",
        "VOTER_REWARD_MIN_DECISIVE_VOTES": 1,
        "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE": True,
        "VOTER_REWARD_APPROVAL_SIDE": "original",
        "VOTER_REWARD_REJECTION_SIDE": "not_original",
    },
    "production": {
        "VOTER_REWARDS_ENABLED": False,
        "VOTER_REWARD_POOL_PER_DECISION_ZOID": "1",
        "VOTER_REWARD_MAX_PER_WALLET_ZOID": "0",
        "VOTER_REWARD_MIN_DECISIVE_VOTES": 1,
        "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE": True,
        "VOTER_REWARD_APPROVAL_SIDE": "original",
        "VOTER_REWARD_REJECTION_SIDE": "not_original",
    },
}

VALID_ACCESS_CONTROL_MODES = {"open", "invite_only", "allowlist", "disabled"}

_ACCESS_CONTROL_DEFAULTS = {
    "development": {
        "ACCESS_CONTROL_MODE": "open",
        "ACCESS_REQUESTS_ENABLED": True,
        "ACCESS_DEV_BYPASS_ENABLED": True,
        "REQUIRE_ACCESS_FOR_APP": False,
        "REQUIRE_ACCESS_FOR_SUBMISSIONS": False,
        "REQUIRE_ACCESS_FOR_VOTES": False,
        "REQUIRE_ACCESS_FOR_REWARDS": False,
        "REQUIRE_ACCESS_FOR_TRANSFERS": False,
        "MAX_WALLETS_PER_ACCESS_ACCOUNT": 5,
        "ACCESS_PUBLIC_LABEL": "Open local development",
    },
    "testnet": {
        "ACCESS_CONTROL_MODE": "invite_only",
        "ACCESS_REQUESTS_ENABLED": True,
        "ACCESS_DEV_BYPASS_ENABLED": False,
        "REQUIRE_ACCESS_FOR_APP": True,
        "REQUIRE_ACCESS_FOR_SUBMISSIONS": True,
        "REQUIRE_ACCESS_FOR_VOTES": True,
        "REQUIRE_ACCESS_FOR_REWARDS": True,
        "REQUIRE_ACCESS_FOR_TRANSFERS": True,
        "MAX_WALLETS_PER_ACCESS_ACCOUNT": 1,
        "ACCESS_PUBLIC_LABEL": "Controlled invite-only testnet",
    },
    "production": {
        "ACCESS_CONTROL_MODE": "invite_only",
        "ACCESS_REQUESTS_ENABLED": True,
        "ACCESS_DEV_BYPASS_ENABLED": False,
        "REQUIRE_ACCESS_FOR_APP": True,
        "REQUIRE_ACCESS_FOR_SUBMISSIONS": True,
        "REQUIRE_ACCESS_FOR_VOTES": True,
        "REQUIRE_ACCESS_FOR_REWARDS": True,
        "REQUIRE_ACCESS_FOR_TRANSFERS": True,
        "MAX_WALLETS_PER_ACCESS_ACCOUNT": 1,
        "ACCESS_PUBLIC_LABEL": "Controlled invite-only network",
    },
}


def _clean_path(value):
    cleaned = (value or ".").strip()
    return cleaned or "."


def build_data_paths(data_dir):
    data_dir = _clean_path(data_dir)
    temp_dir = os.path.join(data_dir, "temp")
    content_storage_dir = os.path.join(data_dir, "content")
    return {
        "data_dir": data_dir,
        "blockchain_file": os.path.join(data_dir, "blockchain.json"),
        "peers_file": os.path.join(data_dir, "peers.json"),
        "sqlite_db_path": os.path.join(data_dir, "zoidbergchain.db"),
        "temp_dir": temp_dir,
        "submissions_dir": os.path.join(temp_dir, "submissions"),
        "content_storage_dir": content_storage_dir,
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


def _env_int_any(names, default, *, minimum=None):
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        try:
            parsed = int(str(value).strip())
        except (AttributeError, ValueError) as exc:
            raise ValueError(f"Invalid integer value for {name}: {value!r}.") from exc
        if minimum is not None and parsed < minimum:
            raise ValueError(f"Invalid integer value for {name}: {value!r}.")
        return parsed
    return default


def _env_decimal_string(name, default, *, minimum=Decimal("0")):
    value = os.getenv(name)
    if value is None:
        return str(default)
    candidate = str(value).strip()
    try:
        decimal_value = Decimal(candidate)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value for {name}: {value!r}.") from exc
    if decimal_value < minimum:
        raise ValueError(f"Invalid decimal value for {name}: {value!r}.")
    return candidate


def _split_csv(value):
    if value is None:
        return []
    return [
        item.strip()
        for item in str(value).split(",")
        if item and item.strip()
    ]


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
_CURRENT_VOTER_REWARD_DEFAULTS = _VOTER_REWARD_DEFAULTS[ENVIRONMENT]
_CURRENT_ACCESS_CONTROL_DEFAULTS = _ACCESS_CONTROL_DEFAULTS[ENVIRONMENT]

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
    ("ENABLE_RATE_LIMITING", "RATE_LIMIT_ENABLED", "RATE_LIMITING_ENABLED"),
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
ACCESS_CONTROL_MODE = _env_value_any(
    ("ACCESS_CONTROL_MODE",),
    _CURRENT_ACCESS_CONTROL_DEFAULTS["ACCESS_CONTROL_MODE"],
).strip().lower()
if ACCESS_CONTROL_MODE not in VALID_ACCESS_CONTROL_MODES:
    valid_values = ", ".join(sorted(VALID_ACCESS_CONTROL_MODES))
    raise ValueError(
        f"Invalid ACCESS_CONTROL_MODE value: {ACCESS_CONTROL_MODE!r}. "
        f"Expected one of: {valid_values}."
    )
ACCESS_REQUESTS_ENABLED = _env_flag(
    "ACCESS_REQUESTS_ENABLED",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["ACCESS_REQUESTS_ENABLED"],
)
ACCESS_DEV_BYPASS_ENABLED = (
    _env_flag(
        "ACCESS_DEV_BYPASS_ENABLED",
        _CURRENT_ACCESS_CONTROL_DEFAULTS["ACCESS_DEV_BYPASS_ENABLED"],
    )
    if ENVIRONMENT == "development"
    else False
)
REQUIRE_ACCESS_FOR_APP = _env_flag(
    "REQUIRE_ACCESS_FOR_APP",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["REQUIRE_ACCESS_FOR_APP"],
)
REQUIRE_ACCESS_FOR_SUBMISSIONS = _env_flag(
    "REQUIRE_ACCESS_FOR_SUBMISSIONS",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["REQUIRE_ACCESS_FOR_SUBMISSIONS"],
)
REQUIRE_ACCESS_FOR_VOTES = _env_flag(
    "REQUIRE_ACCESS_FOR_VOTES",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["REQUIRE_ACCESS_FOR_VOTES"],
)
REQUIRE_ACCESS_FOR_REWARDS = _env_flag(
    "REQUIRE_ACCESS_FOR_REWARDS",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["REQUIRE_ACCESS_FOR_REWARDS"],
)
REQUIRE_ACCESS_FOR_TRANSFERS = _env_flag(
    "REQUIRE_ACCESS_FOR_TRANSFERS",
    _CURRENT_ACCESS_CONTROL_DEFAULTS["REQUIRE_ACCESS_FOR_TRANSFERS"],
)
MAX_WALLETS_PER_ACCESS_ACCOUNT = _env_int_any(
    ("MAX_WALLETS_PER_ACCESS_ACCOUNT",),
    _CURRENT_ACCESS_CONTROL_DEFAULTS["MAX_WALLETS_PER_ACCESS_ACCOUNT"],
    minimum=1,
)
ACCESS_PUBLIC_LABEL = _env_value_any(
    ("ACCESS_PUBLIC_LABEL",),
    _CURRENT_ACCESS_CONTROL_DEFAULTS["ACCESS_PUBLIC_LABEL"],
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


def access_control_mode():
    return ACCESS_CONTROL_MODE


def access_requests_enabled():
    return ACCESS_REQUESTS_ENABLED


def access_dev_bypass_enabled():
    return ACCESS_DEV_BYPASS_ENABLED


def require_access_for_app():
    return REQUIRE_ACCESS_FOR_APP


def require_access_for_submissions():
    return REQUIRE_ACCESS_FOR_SUBMISSIONS


def require_access_for_votes():
    return REQUIRE_ACCESS_FOR_VOTES


def require_access_for_rewards():
    return REQUIRE_ACCESS_FOR_REWARDS


def require_access_for_transfers():
    return REQUIRE_ACCESS_FOR_TRANSFERS


def max_wallets_per_access_account():
    return MAX_WALLETS_PER_ACCESS_ACCOUNT


def access_public_label():
    return ACCESS_PUBLIC_LABEL


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


def _load_allowed_cors_origins():
    explicit_origins = _split_csv(os.getenv("CORS_ALLOWED_ORIGINS"))
    if explicit_origins:
        return tuple(dict.fromkeys(explicit_origins))

    frontend_origin = (os.getenv("FRONTEND_ORIGIN") or "").strip()
    if frontend_origin:
        default_origins = [frontend_origin]
        if ENVIRONMENT == "development":
            default_origins = list(DEFAULT_DEVELOPMENT_ORIGINS) + default_origins
        return tuple(dict.fromkeys(default_origins))

    default_origins = list(DEFAULT_PUBLIC_DEMO_ORIGINS)
    if ENVIRONMENT == "development":
        default_origins = list(DEFAULT_DEVELOPMENT_ORIGINS) + default_origins
    return tuple(dict.fromkeys(default_origins))


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
CONTENT_STORAGE_DIR = _env_value("CONTENT_STORAGE_DIR", _DATA_PATHS["content_storage_dir"])
MAX_CONTENT_FILE_SIZE_BYTES = _env_int("MAX_CONTENT_FILE_SIZE_BYTES", 5 * 1024 * 1024)
MAX_TEXT_CONTENT_BYTES = _env_int("MAX_TEXT_CONTENT_BYTES", 256 * 1024)
MAX_CAPTION_LENGTH = _env_int("MAX_CAPTION_LENGTH", 1000)
MAX_FILENAME_LENGTH = _env_int("MAX_FILENAME_LENGTH", 255)
ENABLE_STRICT_MIME_VALIDATION = _env_flag("ENABLE_STRICT_MIME_VALIDATION", True)
SUPPORTED_IMAGE_MIME_TYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)
SUPPORTED_TEXT_MIME_TYPES = (
    "text/plain",
)
SUPPORTED_CONTENT_MIME_TYPES = SUPPORTED_IMAGE_MIME_TYPES + SUPPORTED_TEXT_MIME_TYPES
STORAGE_BACKEND = _env_value("STORAGE_BACKEND", "json").strip().lower()
if STORAGE_BACKEND not in VALID_STORAGE_BACKENDS:
    supported_backends = ", ".join(sorted(VALID_STORAGE_BACKENDS))
    raise ValueError(
        f"Invalid STORAGE_BACKEND value: {STORAGE_BACKEND!r}. "
        f"Expected one of: {supported_backends}."
    )
SQLITE_DB_PATH = _env_value("SQLITE_DB_PATH", _DATA_PATHS["sqlite_db_path"])
LOG_DIR = _clean_path(_env_value("LOG_DIR", os.path.join(DATA_DIR, "logs")))
LOG_LEVEL = _env_value("LOG_LEVEL", "INFO").upper()
API_BASE_URL = _env_value("API_BASE_URL", PUBLIC_NODE_URL)
PUBLIC_DEMO_MODE = _env_flag("PUBLIC_DEMO_MODE", ENVIRONMENT in {"testnet", "production"})
VOTER_REWARDS_ENABLED = _env_flag(
    "VOTER_REWARDS_ENABLED",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARDS_ENABLED"],
)
VOTER_REWARD_POOL_PER_DECISION_ZOID = _env_decimal_string(
    "VOTER_REWARD_POOL_PER_DECISION_ZOID",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_POOL_PER_DECISION_ZOID"],
)
VOTER_REWARD_MAX_PER_WALLET_ZOID = _env_decimal_string(
    "VOTER_REWARD_MAX_PER_WALLET_ZOID",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_MAX_PER_WALLET_ZOID"],
)
VOTER_REWARD_MIN_DECISIVE_VOTES = _env_int(
    "VOTER_REWARD_MIN_DECISIVE_VOTES",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_MIN_DECISIVE_VOTES"],
)
if VOTER_REWARD_MIN_DECISIVE_VOTES < 1:
    raise ValueError("VOTER_REWARD_MIN_DECISIVE_VOTES must be at least 1.")
VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE = _env_flag(
    "VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_REQUIRE_REVIEW_ELIGIBLE"],
)
VOTER_REWARD_APPROVAL_SIDE = _env_value(
    "VOTER_REWARD_APPROVAL_SIDE",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_APPROVAL_SIDE"],
).strip().lower()
VOTER_REWARD_REJECTION_SIDE = _env_value(
    "VOTER_REWARD_REJECTION_SIDE",
    _CURRENT_VOTER_REWARD_DEFAULTS["VOTER_REWARD_REJECTION_SIDE"],
).strip().lower()
if VOTER_REWARD_APPROVAL_SIDE not in {"original"}:
    raise ValueError("VOTER_REWARD_APPROVAL_SIDE must be 'original'.")
if VOTER_REWARD_REJECTION_SIDE not in {"not_original"}:
    raise ValueError("VOTER_REWARD_REJECTION_SIDE must be 'not_original'.")
CORS_ALLOWED_ORIGINS = _load_allowed_cors_origins()

validate_peer_auth_config()


def cors_allowed_origins():
    return list(CORS_ALLOWED_ORIGINS)


def public_demo_mode_enabled():
    return PUBLIC_DEMO_MODE
