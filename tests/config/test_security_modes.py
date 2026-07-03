import importlib
import os
from contextlib import contextmanager

import pytest


_CONFIG_ENV_KEYS = (
    "ENVIRONMENT",
    "APP_ENV",
    "ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT",
    "ALLOW_DEV_RESET_ENDPOINTS",
    "ALLOW_INSECURE_LOCAL_PEERS",
    "ENABLE_RATE_LIMITING",
    "RATE_LIMIT_ENABLED",
    "REQUIRE_PEER_AUTH",
    "PUBLIC_API_MODE",
    "PEER_SHARED_SECRET",
)


@contextmanager
def loaded_config(**environment_values):
    previous_values = {key: os.environ.get(key) for key in _CONFIG_ENV_KEYS}
    try:
        for key in _CONFIG_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in environment_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        if (
            environment_values.get("ENVIRONMENT", "development") in {"testnet", "production"}
            and "PEER_SHARED_SECRET" not in environment_values
        ):
            os.environ["PEER_SHARED_SECRET"] = "super-secret-value"

        import config

        yield importlib.reload(config)
    finally:
        for key, value in previous_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        import config

        importlib.reload(config)


def test_default_environment_is_development():
    with loaded_config() as config:
        assert config.ENVIRONMENT == "development"
        assert config.APP_ENV == "development"
        assert config.is_development()
        assert not config.is_testnet()
        assert not config.is_production()


def test_development_allows_dev_private_key_export():
    with loaded_config(ENVIRONMENT="development") as config:
        assert config.ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT is True
        assert config.allow_private_key_export() is True


@pytest.mark.parametrize("environment", ["testnet", "production"])
def test_public_environments_block_private_key_export(environment):
    with loaded_config(ENVIRONMENT=environment) as config:
        assert config.ALLOW_DEV_WALLET_PRIVATE_KEY_EXPORT is False
        assert config.allow_private_key_export() is False


@pytest.mark.parametrize(
    ("environment", "expected_rate_limiting"),
    [
        ("development", False),
        ("testnet", True),
        ("production", True),
    ],
)
def test_rate_limiting_default_differs_by_environment(environment, expected_rate_limiting):
    with loaded_config(ENVIRONMENT=environment) as config:
        assert config.ENABLE_RATE_LIMITING is expected_rate_limiting
        assert config.RATE_LIMIT_ENABLED is expected_rate_limiting
        assert config.rate_limiting_enabled() is expected_rate_limiting


@pytest.mark.parametrize(
    ("environment", "expected_peer_auth"),
    [
        ("development", False),
        ("testnet", True),
        ("production", True),
    ],
)
def test_peer_auth_requirement_differs_by_environment(environment, expected_peer_auth):
    with loaded_config(ENVIRONMENT=environment) as config:
        assert config.REQUIRE_PEER_AUTH is expected_peer_auth
        assert config.require_peer_auth() is expected_peer_auth


def test_helper_functions_return_correct_values_for_testnet():
    with loaded_config(ENVIRONMENT="testnet") as config:
        assert config.is_testnet()
        assert not config.is_development()
        assert not config.is_production()
        assert config.public_api_mode_enabled() is True
        assert config.require_peer_auth() is True
        assert config.allow_private_key_export() is False
        assert config.allow_dev_reset_endpoints() is False
        assert config.allow_insecure_local_peers() is False


def test_invalid_environment_value_fails_clearly():
    with pytest.raises(ValueError, match="Invalid ENVIRONMENT value"):
        with loaded_config(ENVIRONMENT="staging"):
            pass


def test_peer_auth_requires_non_default_secret_in_public_modes():
    with pytest.raises(ValueError, match="PEER_SHARED_SECRET must be set"):
        with loaded_config(ENVIRONMENT="testnet", PEER_SHARED_SECRET="change-me"):
            pass

    with pytest.raises(ValueError, match="PEER_SHARED_SECRET must be set"):
        with loaded_config(ENVIRONMENT="production", PEER_SHARED_SECRET=""):
            pass


def test_development_allows_peer_auth_secret_to_be_missing():
    with loaded_config(ENVIRONMENT="development", PEER_SHARED_SECRET="") as config:
        assert config.REQUIRE_PEER_AUTH is False
