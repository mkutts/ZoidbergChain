import importlib

import pytest

import config


def test_storage_backend_json_selected_by_default(monkeypatch, isolated_data_dir):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    importlib.reload(config)

    from storage import JSONStorageBackend, create_storage_backend

    backend = create_storage_backend()

    assert isinstance(backend, JSONStorageBackend)


def test_storage_backend_sqlite_selected(monkeypatch, isolated_data_dir):
    monkeypatch.setenv("STORAGE_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_DB_PATH", str(isolated_data_dir / "node.db"))
    importlib.reload(config)

    from storage import SQLiteStorageBackend, create_storage_backend

    backend = create_storage_backend()

    assert isinstance(backend, SQLiteStorageBackend)


def test_invalid_storage_backend_fails_clearly(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "bad-value")

    with pytest.raises(ValueError, match="Invalid STORAGE_BACKEND value"):
        importlib.reload(config)

    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    importlib.reload(config)
