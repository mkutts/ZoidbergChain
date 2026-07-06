from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from config import BLOCKCHAIN_FILE, PEERS_FILE, STORAGE_BACKEND


SUPPORTED_STORAGE_BACKENDS = {"json"}


class StorageBackend(ABC):
    def __init__(self, blockchain_file: str = BLOCKCHAIN_FILE, peers_file: str = PEERS_FILE):
        self.blockchain_file = blockchain_file
        self.peers_file = peers_file

    @abstractmethod
    def load_blockchain_document(self) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        raise NotImplementedError

    def delete_blockchain_document(self) -> None:
        if os.path.exists(self.blockchain_file):
            os.remove(self.blockchain_file)

    def load_chain(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("chain", [])

    def save_chain(self, chain) -> None:
        document = self._load_or_new_blockchain_document()
        document["chain"] = chain
        self.save_blockchain_document(document)

    def load_wallets(self):
        document = self.load_blockchain_document()
        if not document:
            return {}
        return document.get("wallets", {})

    def save_wallets(self, wallets) -> None:
        document = self._load_or_new_blockchain_document()
        document["wallets"] = wallets
        self.save_blockchain_document(document)

    def load_submissions(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("submissions", [])

    def save_submissions(self, submissions) -> None:
        document = self._load_or_new_blockchain_document()
        document["submissions"] = submissions
        self.save_blockchain_document(document)

    def load_mint_queue(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("mint_queue", [])

    def save_mint_queue(self, mint_queue) -> None:
        document = self._load_or_new_blockchain_document()
        document["mint_queue"] = mint_queue
        self.save_blockchain_document(document)

    def load_votes(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("votes", [])

    def save_votes(self, votes) -> None:
        document = self._load_or_new_blockchain_document()
        document["votes"] = votes
        self.save_blockchain_document(document)

    def load_certificates(self):
        document = self.load_blockchain_document()
        if not document:
            return []
        return document.get("originality_certificates", [])

    def save_certificates(self, certificates) -> None:
        document = self._load_or_new_blockchain_document()
        document["originality_certificates"] = certificates
        self.save_blockchain_document(document)

    def load_blockchain_state(self):
        return self.load_blockchain_document()

    def save_blockchain_state(self, state: dict[str, Any]) -> None:
        self.save_blockchain_document(state)

    def load_peers(self):
        raise NotImplementedError

    def save_peers(self, peers) -> None:
        raise NotImplementedError

    def _load_or_new_blockchain_document(self) -> dict[str, Any]:
        document = self.load_blockchain_document()
        if isinstance(document, dict):
            return deepcopy(document)
        return {}


class JSONStorageBackend(StorageBackend):
    def load_blockchain_document(self) -> dict[str, Any] | None:
        if not os.path.exists(self.blockchain_file):
            return None

        try:
            with open(self.blockchain_file, "r", encoding="utf-8") as blockchain_file:
                document = json.load(blockchain_file)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(document, dict):
            return None

        return document

    def save_blockchain_document(self, document: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.blockchain_file) or ".", exist_ok=True)
        with open(self.blockchain_file, "w", encoding="utf-8") as blockchain_file:
            json.dump(document, blockchain_file, indent=4)

    def load_peers(self):
        if not os.path.exists(self.peers_file):
            return []

        try:
            with open(self.peers_file, "r", encoding="utf-8") as peer_file:
                peers = json.load(peer_file)
        except (json.JSONDecodeError, OSError):
            return []

        if not isinstance(peers, list):
            return []

        return peers

    def save_peers(self, peers) -> None:
        os.makedirs(os.path.dirname(self.peers_file) or ".", exist_ok=True)
        with open(self.peers_file, "w", encoding="utf-8") as peer_file:
            json.dump(peers, peer_file, indent=4)


def create_storage_backend(name: str | None = None, **kwargs) -> StorageBackend:
    backend_name = (name or STORAGE_BACKEND or "json").strip().lower()
    if backend_name == "json":
        return JSONStorageBackend(**kwargs)
    supported = ", ".join(sorted(SUPPORTED_STORAGE_BACKENDS))
    raise ValueError(
        f"Unsupported STORAGE_BACKEND value: {backend_name!r}. "
        f"Supported values: {supported}."
    )
