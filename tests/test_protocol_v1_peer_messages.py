from __future__ import annotations

import pytest

from protocol_v1_peer_message import (
    ProtocolV1PeerReplayStore,
    ReplayedPeerMessageError,
    calculate_protocol_v1_peer_message_id,
    protocol_v1_peer_envelope_text,
    sign_protocol_v1_peer_message,
)


def test_protocol_v1_peer_message_golden_vectors_are_literal_and_stable():
    payload = {
        "network_name": "zoidberg-testnet",
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
    }
    kwargs = {
        "network_id": "zoidberg-public-testnet-v1",
        "message_type": "peer-registration",
        "sender_node_id": "peer-node-1",
        "timestamp": 1_724_760_000,
        "nonce": "peer-nonce-1",
    }

    assert protocol_v1_peer_envelope_text(payload, **kwargs) == (
        '{"domain":"zoidbergchain/peer-message/v1","message_type":"peer-registration",'
        '"network_id":"zoidberg-public-testnet-v1","nonce":"peer-nonce-1","object_type":"peer-message",'
        '"payload":{"network_name":"zoidberg-testnet","node_id":"peer-node-1","url":"http://peer-one.test:8000"},'
        '"peer_message_version":1,"protocol":"zoidbergchain","protocol_version":1,'
        '"sender_node_id":"peer-node-1","timestamp":1724760000}'
    )
    assert calculate_protocol_v1_peer_message_id(payload, **kwargs) == (
        "89e78f2e47da978dd21a744c745cf2c35d118b04facd07f43f4c6f87dd16bfb9"
    )
    assert sign_protocol_v1_peer_message(payload, secret="test-only-peer-secret", **kwargs) == (
        "ebba943b7ee8c924ff1034ae65ae494ae37f0e9609399f12844eaaa7059dd4b9"
    )


def test_protocol_v1_peer_message_mutation_vectors_change_id_and_auth():
    payload = {
        "network_name": "zoidberg-testnet",
        "node_id": "peer-node-1",
        "url": "http://peer-one.test:8000",
    }
    kwargs = {
        "network_id": "zoidberg-public-testnet-v1",
        "message_type": "peer-registration",
        "sender_node_id": "peer-node-1",
        "timestamp": 1_724_760_000,
        "nonce": "peer-nonce-1",
    }

    assert calculate_protocol_v1_peer_message_id(
        payload,
        **{**kwargs, "network_id": "zoidberg-devnet-v1"},
    ) == "9c7414fc5bfbf70096d5133d257f8c58f39d952cdcca2dce0ad6682f24eb2e2f"
    assert sign_protocol_v1_peer_message(
        payload,
        secret="test-only-peer-secret",
        **{**kwargs, "network_id": "zoidberg-devnet-v1"},
    ) == "43063e3e4f14e19d1fdff908750792fa56206e44d91f722c5707fdfbb768239c"
    assert calculate_protocol_v1_peer_message_id(
        payload,
        **{**kwargs, "message_type": "submission"},
    ) == "d910e09c9db54e314e1cb06b89b05541799c4df9d01145b6fbb77d48b4f88a15"
    assert sign_protocol_v1_peer_message(
        payload,
        secret="test-only-peer-secret",
        **{**kwargs, "message_type": "submission"},
    ) == "6f3c0faccb7fef0a5a7b95100b9ef5f9dcd69cf0a735c434ea4b0a11cd762b5e"
    assert calculate_protocol_v1_peer_message_id(
        payload,
        **{**kwargs, "sender_node_id": "peer-node-2"},
    ) == "ea32b6b49fd69eea48b84c3626aca5f51b03bebc435b637b4502eb123e594bef"
    assert sign_protocol_v1_peer_message(
        payload,
        secret="test-only-peer-secret",
        **{**kwargs, "sender_node_id": "peer-node-2"},
    ) == "889315faf654ba5e7d97feb227131d1c0296441bac55d7e03c2eb52079df183b"
    assert calculate_protocol_v1_peer_message_id(
        {
            "network_name": "zoidberg-testnet",
            "node_id": "peer-node-1",
            "url": "http://peer-two.test:8000",
        },
        **kwargs,
    ) == "3280b7f8e1973699c28fc6e182bf94b924dbc7f578a8a621ce5ed17c9cf7a6cf"
    assert sign_protocol_v1_peer_message(
        {
            "network_name": "zoidberg-testnet",
            "node_id": "peer-node-1",
            "url": "http://peer-two.test:8000",
        },
        secret="test-only-peer-secret",
        **kwargs,
    ) == "9b35c3de21286ce99be5faa2a3dcf595e65bef0c617f042047d9b9df1c787f63"


def test_protocol_v1_peer_payload_float_fields_are_normalized_before_canonicalization():
    payload = {
        "created_at": 1_724_760_000.5,
        "nested": {"score": 9.75},
    }

    assert protocol_v1_peer_envelope_text(
        payload,
        network_id="zoidberg-public-testnet-v1",
        message_type="submission",
        sender_node_id="peer-node-1",
        timestamp=1_724_760_000,
        nonce="peer-nonce-2",
    ) == (
        '{"domain":"zoidbergchain/peer-message/v1","message_type":"submission",'
        '"network_id":"zoidberg-public-testnet-v1","nonce":"peer-nonce-2","object_type":"peer-message",'
        '"payload":{"created_at":"1724760000.5","nested":{"score":"9.75"}},'
        '"peer_message_version":1,"protocol":"zoidbergchain","protocol_version":1,'
        '"sender_node_id":"peer-node-1","timestamp":1724760000}'
    )


def test_protocol_v1_peer_replay_store_persists_across_restart_and_prunes_expired_entries(isolated_data_dir):
    replay_file = isolated_data_dir / "peer-replay-state.json"
    store = ProtocolV1PeerReplayStore(
        replay_file,
        retention_window_seconds=300,
    )
    kwargs = {
        "sender_node_id": "peer-node-1",
        "nonce": "peer-nonce-1",
        "message_id": "89e78f2e47da978dd21a744c745cf2c35d118b04facd07f43f4c6f87dd16bfb9",
        "timestamp": 1_724_760_000,
        "now": 1_724_760_000,
    }

    store.reject_replay_or_record(**kwargs)
    assert replay_file.exists()
    assert store.list_entries(now=1_724_760_100) == [
        {
            "sender_node_id": "peer-node-1",
            "nonce": "peer-nonce-1",
            "message_id": "89e78f2e47da978dd21a744c745cf2c35d118b04facd07f43f4c6f87dd16bfb9",
            "timestamp": 1_724_760_000,
            "expires_at": 1_724_760_300,
        }
    ]

    reloaded_store = ProtocolV1PeerReplayStore(
        replay_file,
        retention_window_seconds=300,
    )
    with pytest.raises(ReplayedPeerMessageError, match="Replayed peer message"):
        reloaded_store.reject_replay_or_record(**kwargs)

    assert reloaded_store.list_entries(now=1_724_760_301) == []
