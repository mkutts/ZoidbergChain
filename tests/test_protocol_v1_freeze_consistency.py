from __future__ import annotations

import json
from pathlib import Path

from block import PROTOCOL_V1_BLOCK_VERSION
from config import PROTOCOL_V1_CONFIRMATION_DEPTH, PROTOCOL_V1_FINALITY_DEPTH
from protocol_v1 import OBJECT_DOMAINS, PROTOCOL_NAME, PROTOCOL_VERSION, PUBLIC_TESTNET_V1_NETWORK_ID
from protocol_v1_genesis import (
    PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTE_LENGTH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_CONTENT_TYPE,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH,
    PUBLIC_TESTNET_V1_GENESIS_MEDIA_MIME_TYPE,
    PUBLIC_TESTNET_V1_GENESIS_VERSION,
)
from protocol_v1_native_transfer import PROTOCOL_V1_NATIVE_TRANSFER_VERSION
from protocol_v1_originality import PROTOCOL_V1_CERTIFICATE_VERSION, PROTOCOL_V1_VOTE_VERSION
from protocol_v1_peer_message import PROTOCOL_V1_PEER_AUTH_ALGORITHM, PROTOCOL_V1_PEER_MESSAGE_VERSION


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "docs" / "protocol-v1-freeze-report.json"
SPEC_PATH = REPO_ROOT / "docs" / "protocol-v1.md"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "protocol_v1_golden_vectors.json"
README_PATH = REPO_ROOT / "README.md"
PER_AREA_DOCS = [
    REPO_ROOT / "docs" / "protocol-v1-audit.md",
    REPO_ROOT / "docs" / "protocol-v1-canonical-serialization.md",
    REPO_ROOT / "docs" / "protocol-v1-block-format.md",
    REPO_ROOT / "docs" / "protocol-v1-originality-and-votes.md",
    REPO_ROOT / "docs" / "protocol-v1-native-transfers.md",
    REPO_ROOT / "docs" / "protocol-v1-peer-messages.md",
    REPO_ROOT / "docs" / "protocol-v1-lifecycle-finality.md",
    REPO_ROOT / "docs" / "protocol-v1-genesis-reset.md",
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_freeze_report_matches_runtime_constants():
    report = _load_json(REPORT_PATH)

    assert report["protocol_name"] == PROTOCOL_NAME
    assert report["protocol_version"] == PROTOCOL_VERSION
    assert report["version_tag"] == "v1"
    assert report["network_id"] == PUBLIC_TESTNET_V1_NETWORK_ID
    assert report["genesis_hash"] == PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH
    assert report["genesis_media"]["present"] is True
    assert report["genesis_media"]["media_hash"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH
    assert report["genesis_media"]["mime_type"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_MIME_TYPE
    assert report["genesis_media"]["content_type"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_CONTENT_TYPE
    assert report["genesis_media"]["byte_length"] == PUBLIC_TESTNET_V1_GENESIS_MEDIA_BYTE_LENGTH
    assert report["confirmation_depth"] == PROTOCOL_V1_CONFIRMATION_DEPTH
    assert report["finality_depth"] == PROTOCOL_V1_FINALITY_DEPTH
    assert report["objects"]["block"]["object_version"] == PROTOCOL_V1_BLOCK_VERSION
    assert report["objects"]["vote"]["object_version"] == PROTOCOL_V1_VOTE_VERSION
    assert report["objects"]["certificate"]["object_version"] == PROTOCOL_V1_CERTIFICATE_VERSION
    assert report["objects"]["native_transfer"]["object_version"] == PROTOCOL_V1_NATIVE_TRANSFER_VERSION
    assert report["objects"]["peer_message"]["object_version"] == PROTOCOL_V1_PEER_MESSAGE_VERSION
    assert report["objects"]["genesis"]["object_version"] == PUBLIC_TESTNET_V1_GENESIS_VERSION
    assert report["objects"]["peer_message"]["auth_algorithm"] == PROTOCOL_V1_PEER_AUTH_ALGORITHM


def test_freeze_report_domains_match_protocol_domains_and_fixture():
    report = _load_json(REPORT_PATH)
    fixture = _load_json(FIXTURE_PATH)

    assert report["objects"]["block"]["domain"] == OBJECT_DOMAINS["block"]
    assert report["objects"]["vote"]["domain"] == OBJECT_DOMAINS["vote"]
    assert report["objects"]["certificate"]["domain"] == OBJECT_DOMAINS["originality-certificate"]
    assert report["objects"]["native_transfer"]["domain"] == OBJECT_DOMAINS["native-transfer"]
    assert report["objects"]["peer_message"]["domain"] == OBJECT_DOMAINS["peer-message"]
    assert report["objects"]["genesis"]["domain"] == OBJECT_DOMAINS["genesis"]
    assert report["genesis_hash"] == fixture["genesis"]["hash"]
    assert report["network_id"] == fixture["protocol"]["network_id"]


def test_authoritative_spec_exists_and_contains_required_frozen_identity():
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "## 1. Scope and status" in spec
    assert "## 23. Known limitations" in spec
    assert "zoidberg-public-testnet-v1" in spec
    assert f"PUBLIC TESTNET V1 GENESIS HASH = {PUBLIC_TESTNET_V1_CANONICAL_GENESIS_HASH}" in spec
    assert PUBLIC_TESTNET_V1_GENESIS_MEDIA_HASH in spec
    assert "exact original Zoidberg genesis meme bytes recovered from the pre-v1 genesis record" in spec
    assert "Native ZOID transfers are Layer 1 ZoidbergChain transactions and are not Ethereum/ERC-20 transactions." in spec
    assert "Peer authentication never bypasses inner-object validation." in spec


def test_per_area_docs_and_readme_defer_to_authoritative_spec():
    for path in PER_AREA_DOCS:
        assert "docs/protocol-v1.md" in path.read_text(encoding="utf-8")

    assert "docs/protocol-v1.md" in README_PATH.read_text(encoding="utf-8")


def test_freeze_report_records_model_a_and_legacy_boundaries():
    report = _load_json(REPORT_PATH)

    assert report["model_a"]["embedded_media_bytes_required"] is True
    assert report["model_a"]["media_bytes_hash_critical"] is True
    assert report["model_a"]["cache_deletion_preserves_authoritative_media"] is True
    assert report["model_a"]["peer_sync_preserves_media"] is True
    assert report["model_a"]["legacy_blocks_satisfy_model_a"] is False
    assert report["legacy_boundaries"]["legacy_direct_block_route"]["path"] == "/add_block"
    assert report["legacy_boundaries"]["legacy_direct_block_route"]["mode"] == "development_only"
    assert report["legacy_boundaries"]["legacy_direct_block_route"]["allowed_in_public_testnet"] is False
