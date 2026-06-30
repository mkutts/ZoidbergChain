import json
import os
import time
from urllib.parse import urlparse

from config import PEERS_FILE

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
    def __init__(self, file_path=PEERS_FILE):
        self.file_path = file_path

    def list_peers(self):
        return self._load_peers()

    def list_active_peers(self, network_name=None):
        peers = [
            peer
            for peer in self._load_peers()
            if peer.get("status") == ACTIVE
        ]
        if network_name:
            peers = [
                peer
                for peer in peers
                if peer.get("network_name") == network_name
            ]
        return peers

    def get_active_peer(self, node_id):
        if not isinstance(node_id, str) or not node_id.strip():
            return None

        for peer in self.list_active_peers():
            if peer.get("node_id") == node_id.strip():
                return peer
        return None

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
        for index, existing_peer in enumerate(peers):
            if existing_peer.get("node_id") == peer["node_id"]:
                peers[index] = {
                    **existing_peer,
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
        if not os.path.exists(self.file_path):
            return []

        try:
            with open(self.file_path, "r") as peer_file:
                peers = json.load(peer_file)
        except json.JSONDecodeError:
            return []

        if not isinstance(peers, list):
            return []

        return [
            peer
            for peer in peers
            if isinstance(peer, dict)
            and peer.get("status") in VALID_PEER_STATUSES
        ]

    def _save_peers(self, peers):
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w") as peer_file:
            json.dump(peers, peer_file, indent=4)
