import time
from urllib.parse import urlparse

from config import PEERS_FILE
from storage import create_storage_backend

ACTIVE = "active"
INACTIVE = "inactive"
VALID_PEER_STATUSES = {ACTIVE, INACTIVE}


def normalize_peer_url(url):
    if not isinstance(url, str):
        raise ValueError("Peer URL is required.")

    normalized = url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Peer URL must be a valid http or https URL.")

    return normalized


class PeerStore:
    def __init__(self, file_path=PEERS_FILE, storage_backend=None, sqlite_db_path=None):
        self.storage = storage_backend or create_storage_backend(
            peers_file=file_path,
            sqlite_db_path=sqlite_db_path,
        )

    def list_peers(self):
        return self._load_peers()

    def list_active_peers(self, network_name=None):
        return self.storage.list_active_peers(
            peers=self._load_peers(),
            network_name=network_name,
        )

    def get_active_peer(self, node_id):
        if not isinstance(node_id, str) or not node_id.strip():
            return None

        return self.storage.get_peer(node_id, self.list_active_peers())

    def register_peer(self, node_id, url, network_name, now=None):
        if not isinstance(node_id, str) or not node_id.strip():
            raise ValueError("Peer node_id is required.")
        if not isinstance(network_name, str) or not network_name.strip():
            raise ValueError("Peer network_name is required.")

        peer = {
            "node_id": node_id.strip(),
            "url": normalize_peer_url(url),
            "network_name": network_name.strip(),
            "last_seen": now if now is not None else time.time(),
            "status": ACTIVE,
        }

        peers = self._load_peers()
        existing_peer = self.storage.get_peer(peer["node_id"], peers)
        if existing_peer is not None:
            for index, existing in enumerate(peers):
                if existing.get("node_id") == peer["node_id"]:
                    peers[index] = {
                        **existing,
                        "url": peer["url"],
                        "network_name": peer["network_name"],
                        "last_seen": peer["last_seen"],
                        "status": ACTIVE,
                    }
                    self._save_peers(peers)
                    return peers[index]

        peers.append(peer)
        self._save_peers(peers)
        return peer

    def _load_peers(self):
        peers = self.storage.load_peers()

        if not isinstance(peers, list):
            return []

        return [
            peer
            for peer in peers
            if isinstance(peer, dict)
            and peer.get("status") in VALID_PEER_STATUSES
        ]

    def _save_peers(self, peers):
        self.storage.save_peers(peers)
