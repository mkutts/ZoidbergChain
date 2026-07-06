import importlib

import pytest

import config


def test_invalid_storage_backend_fails_clearly(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")

    with pytest.raises(ValueError, match="Invalid STORAGE_BACKEND value"):
        importlib.reload(config)

    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    importlib.reload(config)
