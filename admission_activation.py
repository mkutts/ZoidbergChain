"""Persistent, network-scoped admission activation boundary.

The file is a node's fixed protocol configuration.  The blockchain document
also records the value so removing or changing the file cannot relax rules on
restart after activation has been configured.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


ACTIVATION_CONFIG_VERSION = 1
ACTIVATION_FILE_NAME = "admission-activation-v1.json"


def activation_record(height: int, *, network_id: str, genesis_hash: str) -> dict:
    if type(height) is not int or height < 1:
        raise ValueError("Admission activation height must be an integer of at least 1.")
    if not isinstance(network_id, str) or not network_id:
        raise ValueError("Admission activation network ID is required.")
    if not isinstance(genesis_hash, str) or not genesis_hash:
        raise ValueError("Admission activation genesis hash is required.")
    return {
        "config_version": ACTIVATION_CONFIG_VERSION,
        "network_id": network_id,
        "genesis_hash": genesis_hash,
        "activation_height": height,
    }


class AdmissionActivationStore:
    def __init__(self, data_dir: str, *, network_id: str, genesis_hash: str):
        self.path = Path(data_dir) / ACTIVATION_FILE_NAME
        self.network_id = network_id
        self.genesis_hash = genesis_hash

    def read(self) -> dict | None:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                record = json.load(handle)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise ValueError("Admission activation configuration cannot be read.") from exc
        if not isinstance(record, dict):
            raise ValueError("Admission activation configuration is malformed.")
        expected = activation_record(record.get("activation_height"),
                                     network_id=self.network_id, genesis_hash=self.genesis_hash)
        if record != expected:
            raise ValueError("Admission activation configuration conflicts with this network or genesis.")
        return expected

    def configure(self, height: int) -> dict:
        record = activation_record(height, network_id=self.network_id,
                                   genesis_hash=self.genesis_hash)
        existing = self.read()
        if existing is not None:
            if existing != record:
                raise ValueError("Admission activation height is already fixed to another value.")
            return existing
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            existing = self.read()
            if existing != record:
                raise ValueError("Admission activation height was concurrently set to another value.")
        return record

    def verify_document(self, document: dict | None, *, chain_tip: int | None = None) -> dict | None:
        configured = self.read()
        persisted = document.get("admission_activation") if isinstance(document, dict) else None
        if persisted is not None:
            if configured is None or persisted != configured:
                raise ValueError("Persisted admission activation conflicts with network configuration.")
        elif configured is not None and chain_tip is not None and chain_tip >= configured["activation_height"]:
            raise ValueError("Post-activation chain is missing its immutable activation marker.")
        return configured
