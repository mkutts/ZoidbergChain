from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from originality_certificate import (
    OriginalityCertificate,
    build_certificate_identity_payload_v1,
    build_vote_hash_payload_v1,
    calculate_certificate_id,
    calculate_vote_hash,
)
from protocol_v1 import (
    OBJECT_TYPE_NATIVE_TRANSFER,
    OBJECT_TYPE_VOTE,
    PUBLIC_TESTNET_V1_NETWORK_ID,
    canonical_domain_hash,
)
from protocol_v1_originality import (
    PROTOCOL_V1_VOTE_VERSION,
    build_protocol_v1_vote_message,
    build_protocol_v1_vote_message_hash,
    build_protocol_v1_vote_payload,
    build_protocol_v1_vote_signing_payload,
)
from wallet_auth import build_wallet_vote_message, hash_wallet_message, recover_signed_wallet_address


PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
VOTER_WALLET = "0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"
SUBMISSION_ID = "submission-vector-001"
CONTENT_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
NETWORK_ID = PUBLIC_TESTNET_V1_NETWORK_ID
ALT_NETWORK_ID = "zoidberg-devnet-v1"
NONCE = "vote-nonce-001"
ISSUED_AT = "2026-08-27T12:00:00+00:00"
EXPIRES_AT = "2026-08-27T12:05:00+00:00"
ISSUED_AT_DATETIME = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
EXPIRES_AT_DATETIME = datetime(2026, 8, 27, 12, 5, 0, tzinfo=timezone.utc)

VOTE_PAYLOAD_VECTOR = {
    "vote_version": 1,
    "submission_id": SUBMISSION_ID,
    "content_hash": CONTENT_HASH,
    "voter_wallet_address": VOTER_WALLET,
    "vote_type": "original",
    "nonce": NONCE,
    "issued_at": ISSUED_AT,
    "expires_at": EXPIRES_AT,
}

VOTE_SIGNING_PAYLOAD_VECTOR = {
    "domain": "zoidbergchain/vote/v1",
    "network_id": NETWORK_ID,
    "object_type": "vote",
    "payload": {
        "content_hash": CONTENT_HASH,
        "expires_at": EXPIRES_AT,
        "issued_at": ISSUED_AT,
        "nonce": NONCE,
        "submission_id": SUBMISSION_ID,
        "vote_type": "original",
        "vote_version": 1,
        "voter_wallet_address": VOTER_WALLET,
    },
    "protocol": "zoidbergchain",
    "protocol_version": 1,
}

VOTE_MESSAGE_VECTOR = (
    '{"domain":"zoidbergchain/vote/v1","network_id":"zoidberg-public-testnet-v1",'
    '"object_type":"vote","payload":{"content_hash":"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",'
    '"expires_at":"2026-08-27T12:05:00+00:00","issued_at":"2026-08-27T12:00:00+00:00",'
    '"nonce":"vote-nonce-001","submission_id":"submission-vector-001","vote_type":"original",'
    '"vote_version":1,"voter_wallet_address":"0x19e7e376e7c213b7e7e7e46cc70a5dd086daff2a"},'
    '"protocol":"zoidbergchain","protocol_version":1}'
)
VOTE_MESSAGE_HASH_VECTOR = "95d2d5a4b7181aaea73ed284ed88afd3b1cc22b8e699e3cb1f109b98390fc4b2"
ALT_NETWORK_HASH_VECTOR = "e62b898cd0d3138fb581975ea45d697a925a2db7c39d2543028d9c6cc22112b1"
ALT_DOMAIN_HASH_VECTOR = "e3fc2f1d87ded190a57dd2f3ee01f1095c1302dfeddc6133f25c1dfcbe8c5850"
ALT_PROTOCOL_HASH_VECTOR = "80cfdccdd7d2e2c74cc4908787ed36e7cfab26c39b6dd3d4283642ecaa9669c4"
ALT_VOTE_CHOICE_HASH_VECTOR = "5eb469cc5e3d593c7ce9106dc3a0647ec96f5eb1d362c26bb4932c18b9a95fc3"
SIGNATURE_VECTOR = (
    "5b14f579b649f2e95ec5c8541ef7ce20e09881c168891c43f8e954950673ed912b15e73b537d4fc0863b530718ca20e1"
    "652a8e94f7c3c053fa30412bd5c652531b"
)

VOTE_HASH_PAYLOAD_VECTOR = {
    "vote_set_version": 1,
    "submission_id": SUBMISSION_ID,
    "content_hash": CONTENT_HASH,
    "votes": [
        {"voter": "0x1111111111111111111111111111111111111111", "vote_type": "original"},
        {"voter": "0x2222222222222222222222222222222222222222", "vote_type": "original"},
        {"voter": "0x3333333333333333333333333333333333333333", "vote_type": "original"},
        {"voter": "0x4444444444444444444444444444444444444444", "vote_type": "original"},
        {"voter": "0x5555555555555555555555555555555555555555", "vote_type": "not_original"},
    ],
}
VOTE_HASH_VECTOR = "d9b0a5bfd42e2e17cc940abae3ef02fa3282c8fd754f51a6fb151b1a95ba6d2d"

CERTIFICATE_PAYLOAD_VECTOR = {
    "certificate_version": 1,
    "submission_id": SUBMISSION_ID,
    "content_hash": CONTENT_HASH,
    "creator_wallet": VOTER_WALLET,
    "vote_hash": VOTE_HASH_VECTOR,
    "vote_total": 5,
    "decisive_vote_total": 5,
    "original_votes": 4,
    "not_original_votes": 1,
    "unsure_votes": 0,
    "minimum_votes_required": 5,
    "approval_threshold": "0.8",
    "approval_percentage": "0.8",
    "originality_score": "2.3",
}
CERTIFICATE_ID_VECTOR = "78420b3916bde68a5c181dcc4d32046ae332de5e0da81fc7fde8b65fcddf1dff"


def _vector_votes():
    return [
        {"submission_id": SUBMISSION_ID, "voter": "0x1111111111111111111111111111111111111111", "vote_type": "original", "created_at": 1},
        {"submission_id": SUBMISSION_ID, "voter": "0x2222222222222222222222222222222222222222", "vote_type": "original", "created_at": 2},
        {"submission_id": SUBMISSION_ID, "voter": "0x3333333333333333333333333333333333333333", "vote_type": "original", "created_at": 3},
        {"submission_id": SUBMISSION_ID, "voter": "0x4444444444444444444444444444444444444444", "vote_type": "original", "created_at": 4},
        {"submission_id": SUBMISSION_ID, "voter": "0x5555555555555555555555555555555555555555", "vote_type": "not_original", "created_at": 5},
    ]


def _certificate_fields():
    return {
        "certificate_version": 1,
        "protocol_version": 1,
        "network_id": NETWORK_ID,
        "submission_id": SUBMISSION_ID,
        "content_hash": CONTENT_HASH,
        "creator_wallet": VOTER_WALLET,
        "vote_total": 5,
        "decisive_vote_total": 5,
        "original_votes": 4,
        "not_original_votes": 1,
        "unsure_votes": 0,
        "approval_percentage": 0.8,
        "minimum_votes_required": 5,
        "vote_hash": VOTE_HASH_VECTOR,
        "originality_score": 2.3,
        "approval_threshold": 0.8,
        "approved_at": 1724760001.25,
        "issuing_node_id": "node-1",
        "content_id": "ignored-content-id",
        "network_name": "zoidberg-testnet",
    }


def test_protocol_v1_vote_payload_vector_is_literal():
    assert build_protocol_v1_vote_payload(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
    ) == VOTE_PAYLOAD_VECTOR


def test_protocol_v1_vote_signing_payload_and_hash_vectors_are_literal():
    payload = build_protocol_v1_vote_payload(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
    )

    assert build_protocol_v1_vote_signing_payload(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        network_id=NETWORK_ID,
    ) == VOTE_SIGNING_PAYLOAD_VECTOR
    assert build_protocol_v1_vote_message(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        network_id=NETWORK_ID,
    ) == VOTE_MESSAGE_VECTOR
    assert build_protocol_v1_vote_message_hash(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        network_id=NETWORK_ID,
    ) == VOTE_MESSAGE_HASH_VECTOR
    assert hash_wallet_message(VOTE_MESSAGE_VECTOR) == VOTE_MESSAGE_HASH_VECTOR
    assert canonical_domain_hash(payload, object_type=OBJECT_TYPE_NATIVE_TRANSFER, network_id=NETWORK_ID) == ALT_DOMAIN_HASH_VECTOR
    assert canonical_domain_hash(payload, object_type=OBJECT_TYPE_VOTE, network_id=NETWORK_ID, protocol_version=2) == ALT_PROTOCOL_HASH_VECTOR


def test_protocol_v1_vote_signature_recovery_vector_is_literal():
    signature = Account.sign_message(encode_defunct(text=VOTE_MESSAGE_VECTOR), PRIVATE_KEY).signature.hex()

    assert signature == SIGNATURE_VECTOR
    assert recover_signed_wallet_address(VOTE_MESSAGE_VECTOR, signature) == VOTER_WALLET


def test_protocol_v1_vote_network_and_vote_choice_replays_change_hashes():
    assert build_protocol_v1_vote_message_hash(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        network_id=ALT_NETWORK_ID,
    ) == ALT_NETWORK_HASH_VECTOR
    assert build_protocol_v1_vote_message_hash(
        wallet_address=VOTER_WALLET,
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="not_original",
        nonce=NONCE,
        issued_at=ISSUED_AT,
        expires_at=EXPIRES_AT,
        network_id=NETWORK_ID,
    ) == ALT_VOTE_CHOICE_HASH_VECTOR
    assert ALT_NETWORK_HASH_VECTOR != VOTE_MESSAGE_HASH_VECTOR
    assert ALT_VOTE_CHOICE_HASH_VECTOR != VOTE_MESSAGE_HASH_VECTOR
    assert ALT_DOMAIN_HASH_VECTOR != VOTE_MESSAGE_HASH_VECTOR
    assert ALT_PROTOCOL_HASH_VECTOR != VOTE_MESSAGE_HASH_VECTOR


def test_protocol_v1_vote_choice_normalization_rejects_invalid_values():
    with pytest.raises(ValueError, match="Invalid vote type: ORIGINAL"):
        build_protocol_v1_vote_payload(
            wallet_address=VOTER_WALLET,
            submission_id=SUBMISSION_ID,
            content_hash=CONTENT_HASH,
            vote_type="ORIGINAL",
            nonce=NONCE,
            issued_at=ISSUED_AT,
            expires_at=EXPIRES_AT,
        )


def test_protocol_v1_vote_set_hash_vector_is_order_invariant_and_rejects_duplicates():
    votes = _vector_votes()
    reversed_votes = list(reversed(votes))

    assert build_vote_hash_payload_v1(votes, submission_id=SUBMISSION_ID, content_hash=CONTENT_HASH) == VOTE_HASH_PAYLOAD_VECTOR
    assert calculate_vote_hash(votes, vote_set_version=1, submission_id=SUBMISSION_ID, content_hash=CONTENT_HASH, network_id=NETWORK_ID) == VOTE_HASH_VECTOR
    assert calculate_vote_hash(reversed_votes, vote_set_version=1, submission_id=SUBMISSION_ID, content_hash=CONTENT_HASH, network_id=NETWORK_ID) == VOTE_HASH_VECTOR

    duplicate_votes = votes + [
        {
            "submission_id": SUBMISSION_ID,
            "voter": votes[0]["voter"],
            "vote_type": "not_original",
            "created_at": 99,
        }
    ]
    with pytest.raises(ValueError, match="duplicate voters"):
        build_vote_hash_payload_v1(duplicate_votes, submission_id=SUBMISSION_ID, content_hash=CONTENT_HASH)


def test_protocol_v1_certificate_payload_and_id_vectors_are_literal():
    certificate_fields = _certificate_fields()
    mutated_metadata = deepcopy(certificate_fields)
    mutated_metadata["approved_at"] = 1724760999.5
    mutated_metadata["issuing_node_id"] = "node-2"
    mutated_metadata["content_id"] = "other-content-id"

    assert build_certificate_identity_payload_v1(certificate_fields) == CERTIFICATE_PAYLOAD_VECTOR
    assert calculate_certificate_id(
        certificate_fields,
        certificate_version=1,
        network_id=NETWORK_ID,
        network_name="zoidberg-testnet",
    ) == CERTIFICATE_ID_VECTOR
    assert calculate_certificate_id(
        mutated_metadata,
        certificate_version=1,
        network_id=NETWORK_ID,
        network_name="zoidberg-testnet",
    ) == CERTIFICATE_ID_VECTOR


def test_legacy_and_protocol_v1_vote_and_certificate_paths_remain_distinct():
    legacy_message = build_wallet_vote_message(
        wallet_address=VOTER_WALLET,
        network_name="zoidberg-testnet",
        submission_id=SUBMISSION_ID,
        content_hash=CONTENT_HASH,
        vote_type="original",
        nonce=NONCE,
        issued_at=ISSUED_AT_DATETIME,
        expires_at=EXPIRES_AT_DATETIME,
    )
    legacy_certificate = OriginalityCertificate.from_dict(
        {
            "certificate_id": "",
            "submission_id": SUBMISSION_ID,
            "content_hash": CONTENT_HASH,
            "creator_wallet": VOTER_WALLET,
            "vote_total": 5,
            "decisive_vote_total": 5,
            "original_votes": 4,
            "not_original_votes": 1,
            "unsure_votes": 0,
            "approval_percentage": 0.8,
            "minimum_votes_required": 5,
            "approved_at": 1724760001.25,
            "network_name": "zoidberg-testnet",
            "issuing_node_id": "node-1",
            "vote_hash": "c" * 64,
            "originality_score": 2.3,
        }
    )

    assert legacy_message != VOTE_MESSAGE_VECTOR
    assert legacy_certificate.is_protocol_v1_certificate() is False
    assert legacy_certificate.certificate_version is None
    assert legacy_certificate.protocol_version is None
    assert legacy_certificate.network_id is None
    assert legacy_certificate.certificate_id != CERTIFICATE_ID_VECTOR
