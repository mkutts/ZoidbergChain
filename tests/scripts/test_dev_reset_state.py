from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _load_modules(monkeypatch, **env):
    keys = {
        "ENVIRONMENT",
        "PUBLIC_API_MODE",
        "ALLOW_DEV_RESET_ENDPOINTS",
        "DATA_DIR",
        "NODE_DATA_DIR",
        "STORAGE_BACKEND",
        "CONTENT_STORAGE_DIR",
        "PEER_SHARED_SECRET",
    }
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import config
    import scripts.dev_reset_state as dev_reset_state

    importlib.reload(config)
    importlib.reload(dev_reset_state)
    return config, dev_reset_state


def _seed_json_dir(base_dir: Path) -> Path:
    node_dir = base_dir / "json-node"
    node_dir.mkdir(parents=True, exist_ok=True)
    (node_dir / "blockchain.json").write_text(
        json.dumps(
            {
                "chain": [{"index": 0, "hash": "genesis"}],
                "wallets": {"legacy": {"private_key": "secret"}},
                "submissions": [{"submission_id": "sub-1"}],
                "content_objects": [{"content_hash": "hash-1"}],
                "mint_queue": ["sub-1"],
                "votes": [{"submission_id": "sub-1", "voter": "legacy"}],
                "originality_certificates": [{"certificate_id": "cert-1"}],
            }
        ),
        encoding="utf-8",
    )
    (node_dir / "peers.json").write_text(
        json.dumps([{"node_id": "peer-a"}]),
        encoding="utf-8",
    )
    (node_dir / "temp").mkdir(exist_ok=True)
    (node_dir / "temp" / "cache.txt").write_text("cache", encoding="utf-8")
    (node_dir / "content").mkdir(exist_ok=True)
    (node_dir / "content" / "blob.bin").write_bytes(b"blob")
    (node_dir / ".env").write_text("SAFE=1", encoding="utf-8")
    (node_dir / "helper.py").write_text("print('safe')", encoding="utf-8")
    return node_dir


def _seed_sqlite_dir(base_dir: Path) -> Path:
    node_dir = base_dir / "sqlite-node"
    node_dir.mkdir(parents=True, exist_ok=True)
    from storage import SQLiteStorageBackend

    backend = SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))
    backend.save_blockchain_state(
        {
            "chain": [{"index": 0, "hash": "genesis"}],
            "wallets": {"legacy": {"private_key": "secret"}},
            "submissions": [{"submission_id": "sub-1"}],
            "content_objects": [{"content_hash": "hash-1"}],
            "mint_queue": ["sub-1"],
            "votes": [{"submission_id": "sub-1", "voter": "legacy"}],
            "originality_certificates": [{"certificate_id": "cert-1"}],
        }
    )
    backend.save_peers([{"node_id": "peer-a"}])
    (node_dir / "temp").mkdir(exist_ok=True)
    (node_dir / "temp" / "cache.txt").write_text("cache", encoding="utf-8")
    (node_dir / "content").mkdir(exist_ok=True)
    (node_dir / "content" / "blob.bin").write_bytes(b"blob")
    (node_dir / ".env").write_text("SAFE=1", encoding="utf-8")
    (node_dir / "helper.py").write_text("print('safe')", encoding="utf-8")
    return node_dir


def test_reset_refuses_outside_development(monkeypatch, isolated_data_dir):
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="production",
        PUBLIC_API_MODE="true",
        ALLOW_DEV_RESET_ENDPOINTS="false",
        PEER_SHARED_SECRET="prod-secret",
    )

    with pytest.raises(ValueError, match="ENVIRONMENT=development"):
        dev_reset_state.reset_state(
            node_data_dir=isolated_data_dir / "node",
            backend="json",
            confirmation=True,
        )


def test_reset_requires_explicit_confirmation(monkeypatch, isolated_data_dir):
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
    )

    with pytest.raises(ValueError, match="explicit confirmation"):
        dev_reset_state.reset_state(
            node_data_dir=isolated_data_dir / "node",
            backend="json",
            confirmation=False,
        )


def test_reset_refuses_unsafe_project_paths(monkeypatch):
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
    )

    with pytest.raises(ValueError, match="protected workspace path"):
        dev_reset_state.reset_state(
            node_data_dir=dev_reset_state.PROJECT_ROOT / "docs",
            backend="json",
            confirmation=True,
        )


def test_reset_can_reset_isolated_json_data_dir(monkeypatch, isolated_data_dir):
    node_dir = _seed_json_dir(isolated_data_dir)
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
        DATA_DIR=str(node_dir),
        NODE_DATA_DIR=str(node_dir),
        STORAGE_BACKEND="json",
    )

    result = dev_reset_state.reset_state(
        node_data_dir=node_dir,
        backend="json",
        include_content_files=False,
        include_peers=False,
        confirmation=True,
    )

    blockchain_state = json.loads((node_dir / "blockchain.json").read_text(encoding="utf-8"))
    peers_state = json.loads((node_dir / "peers.json").read_text(encoding="utf-8"))

    assert result["backend"] == "json"
    assert blockchain_state["wallets"] == {}
    assert blockchain_state["submissions"] == []
    assert peers_state == [{"node_id": "peer-a"}]
    assert not (node_dir / "temp").exists()
    assert (node_dir / "content" / "blob.bin").exists()


def test_reset_can_reset_isolated_sqlite_data_dir(monkeypatch, isolated_data_dir):
    node_dir = _seed_sqlite_dir(isolated_data_dir)
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
        DATA_DIR=str(node_dir),
        NODE_DATA_DIR=str(node_dir),
        STORAGE_BACKEND="sqlite",
    )

    result = dev_reset_state.reset_state(
        node_data_dir=node_dir,
        backend="sqlite",
        include_content_files=False,
        include_peers=False,
        confirmation=True,
    )

    from storage import SQLiteStorageBackend

    backend = SQLiteStorageBackend(sqlite_db_path=str(node_dir / "zoidbergchain.db"))
    document = backend.load_blockchain_document()

    assert result["backend"] == "sqlite"
    assert document["wallets"] == {}
    assert document["submissions"] == []
    assert backend.load_peers() == [{"node_id": "peer-a"}]
    assert not (node_dir / "temp").exists()
    assert (node_dir / "content" / "blob.bin").exists()


def test_reset_backup_first_creates_backup(monkeypatch, isolated_data_dir):
    node_dir = _seed_json_dir(isolated_data_dir)
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
        DATA_DIR=str(node_dir),
        NODE_DATA_DIR=str(node_dir),
        STORAGE_BACKEND="json",
    )

    result = dev_reset_state.reset_state(
        node_data_dir=node_dir,
        backend="json",
        backup_first_enabled=True,
        confirmation=True,
    )

    assert result["backup"] is not None
    assert Path(result["backup"]["backup_path"]).exists()


def test_reset_include_content_files_removes_only_content_dir(monkeypatch, isolated_data_dir):
    node_dir = _seed_json_dir(isolated_data_dir)
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
        DATA_DIR=str(node_dir),
        NODE_DATA_DIR=str(node_dir),
        STORAGE_BACKEND="json",
        CONTENT_STORAGE_DIR=str(node_dir / "content"),
    )

    dev_reset_state.reset_state(
        node_data_dir=node_dir,
        backend="json",
        include_content_files=True,
        confirmation=True,
    )

    assert not (node_dir / "content").exists()
    assert (node_dir / ".env").exists()
    assert (node_dir / "helper.py").exists()


def test_reset_does_not_delete_env_or_source_files(monkeypatch, isolated_data_dir):
    node_dir = _seed_json_dir(isolated_data_dir)
    _, dev_reset_state = _load_modules(
        monkeypatch,
        ENVIRONMENT="development",
        PUBLIC_API_MODE="false",
        ALLOW_DEV_RESET_ENDPOINTS="true",
        DATA_DIR=str(node_dir),
        NODE_DATA_DIR=str(node_dir),
        STORAGE_BACKEND="json",
    )

    dev_reset_state.reset_state(
        node_data_dir=node_dir,
        backend="json",
        confirmation=True,
    )

    assert (node_dir / ".env").read_text(encoding="utf-8") == "SAFE=1"
    assert (node_dir / "helper.py").read_text(encoding="utf-8") == "print('safe')"
