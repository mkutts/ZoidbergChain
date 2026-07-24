from eth_account import Account
from eth_account.messages import encode_defunct
import pytest

from native_transfer import (
    MAX_TRANSFER_MEMO_LENGTH,
    NATIVE_TRANSFER_ACTION,
    NATIVE_TRANSFER_SIGNATURE_SCHEME,
    NATIVE_TRANSFER_STATUSES,
    NATIVE_TRANSACTION_INITIAL_NONCE,
    NATIVE_TRANSACTION_NONCE_POLICY,
    NATIVE_TRANSACTION_STATUSES,
    NATIVE_TRANSACTION_TYPE,
    build_transfer_signing_message,
    build_native_transaction,
    canonicalize_transaction_payload,
    compute_transaction_id,
    hash_transfer_signing_message,
    normalize_wallet_address,
    parse_transfer_signing_message,
    parse_native_zoid_amount,
    validate_transaction_shape,
    validate_native_transfer_message,
    verify_transfer_signature,
)


NETWORK_NAME = "zoidberg-testnet"


def _wallet_address() -> str:
    return Account.create().address


def _payload(**overrides):
    payload = {
        "action": NATIVE_TRANSFER_ACTION,
        "network": NETWORK_NAME,
        "from_address": _wallet_address(),
        "to_address": _wallet_address(),
        "amount": "1.5",
        "nonce": "1",
        "fee": "0",
        "timestamp": "2026-07-15T15:30:00Z",
        "memo": "native transfer preview",
    }
    payload.update(overrides)
    return payload


def _sign_message(message: str, account) -> str:
    signed = Account.sign_message(encode_defunct(text=message), account.key)
    return signed.signature.hex()


def test_valid_transfer_model_accepted():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    assert transfer.action == NATIVE_TRANSFER_ACTION
    assert transfer.network == NETWORK_NAME
    assert transfer.amount == "1.5"
    assert transfer.fee == "0"
    assert transfer.status == "draft"


def test_invalid_action_rejected():
    with pytest.raises(ValueError, match="action must be exactly"):
        validate_native_transfer_message(
            _payload(action="send_zoid"),
            network_name=NETWORK_NAME,
        )


def test_wrong_network_rejected():
    with pytest.raises(ValueError, match="network does not match"):
        validate_native_transfer_message(
            _payload(network="wrong-network"),
            network_name=NETWORK_NAME,
        )


def test_invalid_from_address_rejected():
    with pytest.raises(ValueError, match="from_address"):
        validate_native_transfer_message(
            _payload(from_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_invalid_to_address_rejected():
    with pytest.raises(ValueError, match="to_address"):
        validate_native_transfer_message(
            _payload(to_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_same_from_and_to_rejected():
    address = _wallet_address()

    with pytest.raises(ValueError, match="must be different"):
        validate_native_transfer_message(
            _payload(from_address=address, to_address=address),
            network_name=NETWORK_NAME,
        )


def test_positive_amount_examples_accepted():
    assert parse_native_zoid_amount("1") == "1"
    assert parse_native_zoid_amount("1.5") == "1.5"
    assert parse_native_zoid_amount("0.000001") == "0.000001"


def test_zero_amount_rejected():
    with pytest.raises(ValueError, match="greater than zero"):
        parse_native_zoid_amount("0")


def test_negative_amount_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        parse_native_zoid_amount("-1")


def test_invalid_decimal_amount_rejected():
    for candidate in ["abc", "NaN", "Infinity"]:
        with pytest.raises(ValueError):
            parse_native_zoid_amount(candidate)


def test_excessive_decimal_precision_rejected():
    with pytest.raises(ValueError, match="precision limit"):
        parse_native_zoid_amount("0.0000001")


def test_fee_zero_accepted():
    transfer = validate_native_transfer_message(
        _payload(fee="0"),
        network_name=NETWORK_NAME,
    )

    assert transfer.fee == "0"


def test_negative_fee_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_native_transfer_message(
            _payload(fee="-0.1"),
            network_name=NETWORK_NAME,
        )


def test_nonce_required():
    with pytest.raises(ValueError, match="nonce is required"):
        validate_native_transfer_message(
            _payload(nonce=None),
            network_name=NETWORK_NAME,
        )


def test_nonce_must_be_positive_integer_starting_at_one():
    for candidate in ["0", "-1", "nonce-1"]:
        with pytest.raises(ValueError):
            validate_native_transfer_message(
                _payload(nonce=candidate),
                network_name=NETWORK_NAME,
            )


def test_timestamp_required_and_validated():
    with pytest.raises(ValueError, match="timestamp is required"):
        validate_native_transfer_message(
            _payload(timestamp=""),
            network_name=NETWORK_NAME,
        )

    with pytest.raises(ValueError, match="ISO 8601"):
        validate_native_transfer_message(
            _payload(timestamp="not-a-timestamp"),
            network_name=NETWORK_NAME,
        )


def test_memo_length_limit_enforced():
    with pytest.raises(ValueError, match="character limit"):
        validate_native_transfer_message(
            _payload(memo="x" * (MAX_TRANSFER_MEMO_LENGTH + 1)),
            network_name=NETWORK_NAME,
        )


def test_transfer_statuses_are_defined_for_future_flow():
    assert NATIVE_TRANSFER_STATUSES == (
        "draft",
        "signed",
        "signed_pending",
        "pending",
        "rejected",
        "included",
        "failed",
    )


def test_transaction_statuses_are_defined_for_future_flow():
    assert NATIVE_TRANSACTION_STATUSES == (
        "signed_pending",
        "validated_pending",
        "mempool",
        "included",
        "settled",
        "rejected",
        "failed",
        "expired",
    )


def test_nonce_policy_constants_match_task_8_2():
    assert NATIVE_TRANSACTION_INITIAL_NONCE == 1
    assert NATIVE_TRANSACTION_NONCE_POLICY == "strict_sequential"


def test_signing_message_is_deterministic():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    first = build_transfer_signing_message(transfer)
    second = build_transfer_signing_message(transfer)

    assert first == second


def test_signing_message_includes_required_fields_and_warning():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)
    message = build_transfer_signing_message(transfer)

    assert "ZoidbergChain Native Transfer" in message
    assert f"Network: {transfer.network}" in message
    assert f"From: {transfer.from_address}" in message
    assert f"To: {transfer.to_address}" in message
    assert f"Amount: {transfer.amount}" in message
    assert f"Fee: {transfer.fee}" in message
    assert f"Nonce: {transfer.nonce}" in message
    assert f"Timestamp: {transfer.timestamp}" in message
    assert "This authorizes a native ZOID transfer on ZoidbergChain." in message
    assert "This is not an Ethereum/ERC-20 transfer." in message


def test_transfer_signing_message_round_trips_back_to_canonical_payload():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)
    parsed = parse_transfer_signing_message(
        build_transfer_signing_message(transfer),
        network_name=NETWORK_NAME,
    )

    assert parsed.from_address == transfer.from_address
    assert parsed.to_address == transfer.to_address
    assert parsed.amount == transfer.amount
    assert parsed.nonce == transfer.nonce
    assert parsed.memo == transfer.memo


def test_message_hash_changes_when_amount_to_or_nonce_changes():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)
    original_hash = hash_transfer_signing_message(build_transfer_signing_message(transfer))

    changed_amount = validate_native_transfer_message(
        _payload(amount="2"),
        network_name=NETWORK_NAME,
    )
    changed_to = validate_native_transfer_message(
        _payload(to_address=_wallet_address()),
        network_name=NETWORK_NAME,
    )
    changed_nonce = validate_native_transfer_message(
        _payload(nonce=2),
        network_name=NETWORK_NAME,
    )

    assert hash_transfer_signing_message(build_transfer_signing_message(changed_amount)) != original_hash
    assert hash_transfer_signing_message(build_transfer_signing_message(changed_to)) != original_hash
    assert hash_transfer_signing_message(build_transfer_signing_message(changed_nonce)) != original_hash


def test_valid_signature_verifies():
    account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, account)

    result = verify_transfer_signature(message, signature, transfer.from_address)

    assert result.verified is True
    assert result.expected_from_address == transfer.from_address
    assert result.recovered_from_address == transfer.from_address
    assert result.signature_scheme == NATIVE_TRANSFER_SIGNATURE_SCHEME
    assert result.signed_message_hash == hash_transfer_signing_message(message)


def test_wrong_signer_rejected():
    account = Account.create()
    wrong_account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, wrong_account)

    with pytest.raises(ValueError, match="does not match"):
        verify_transfer_signature(message, signature, transfer.from_address)


def test_modified_message_rejected():
    account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, account)

    with pytest.raises(ValueError, match="does not match"):
        verify_transfer_signature(message + "\nModified", signature, transfer.from_address)


def test_malformed_signature_rejected():
    transfer = validate_native_transfer_message(_payload(), network_name=NETWORK_NAME)

    with pytest.raises(ValueError, match="Malformed signature"):
        verify_transfer_signature(
            build_transfer_signing_message(transfer),
            "bad-signature",
            transfer.from_address,
        )


def _signed_transaction_payload(**overrides):
    from_account = Account.create()
    transfer = validate_native_transfer_message(
        _payload(from_address=from_account.address),
        network_name=NETWORK_NAME,
    )
    message = build_transfer_signing_message(transfer)
    signature = _sign_message(message, from_account)
    payload = {
        "transaction_type": NATIVE_TRANSACTION_TYPE,
        "network": NETWORK_NAME,
        "from_address": transfer.from_address,
        "to_address": transfer.to_address,
        "amount": transfer.amount,
        "fee": transfer.fee,
        "nonce": transfer.nonce,
        "memo": transfer.memo,
        "timestamp": transfer.timestamp,
        "signature": signature,
        "signature_scheme": NATIVE_TRANSFER_SIGNATURE_SCHEME,
        "signed_message": message,
        "signed_message_hash": hash_transfer_signing_message(message),
        "status": "signed_pending",
        "created_at": "2026-07-15T15:31:00+00:00",
        "updated_at": "2026-07-15T15:31:00+00:00",
    }
    payload.update(overrides)
    return payload


def test_valid_native_transaction_model_accepted():
    transaction = validate_transaction_shape(
        _signed_transaction_payload(),
        network_name=NETWORK_NAME,
    )

    assert transaction.transaction_type == NATIVE_TRANSACTION_TYPE
    assert transaction.network == NETWORK_NAME
    assert transaction.status == "signed_pending"
    assert transaction.amount == "1.5"


def test_invalid_transaction_type_rejected():
    with pytest.raises(ValueError, match="transaction_type must be exactly"):
        validate_transaction_shape(
            _signed_transaction_payload(transaction_type="transfer"),
            network_name=NETWORK_NAME,
        )


def test_invalid_transaction_network_rejected():
    with pytest.raises(ValueError, match="network does not match"):
        validate_transaction_shape(
            _signed_transaction_payload(network="wrong-network"),
            network_name=NETWORK_NAME,
        )


def test_invalid_transaction_from_address_rejected():
    with pytest.raises(ValueError, match="from_address"):
        validate_transaction_shape(
            _signed_transaction_payload(from_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_invalid_transaction_to_address_rejected():
    with pytest.raises(ValueError, match="to_address"):
        validate_transaction_shape(
            _signed_transaction_payload(to_address="not-a-wallet"),
            network_name=NETWORK_NAME,
        )


def test_invalid_transaction_amounts_rejected():
    for candidate in ["abc", "0", "-1"]:
        with pytest.raises(ValueError):
            validate_transaction_shape(
                _signed_transaction_payload(amount=candidate),
                network_name=NETWORK_NAME,
            )


def test_invalid_transaction_fee_rejected():
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_transaction_shape(
            _signed_transaction_payload(fee="-1"),
            network_name=NETWORK_NAME,
        )


def test_unknown_transaction_status_rejected():
    with pytest.raises(ValueError, match="Transaction status must be one of"):
        validate_transaction_shape(
            _signed_transaction_payload(status="mystery"),
            network_name=NETWORK_NAME,
        )


def test_same_signed_payload_produces_same_tx_id():
    payload = _signed_transaction_payload()
    assert compute_transaction_id(payload) == compute_transaction_id(dict(payload))


def test_tx_id_changes_when_core_signed_fields_change():
    payload = _signed_transaction_payload()
    original_tx_id = compute_transaction_id(payload)

    changed_to = dict(payload, to_address=normalize_wallet_address(Account.create().address))
    changed_amount = dict(payload, amount="2")
    changed_nonce = dict(payload, nonce="2")
    changed_signature = dict(payload, signature="0x" + "ab" * 65)

    assert compute_transaction_id(changed_to) != original_tx_id
    assert compute_transaction_id(changed_amount) != original_tx_id
    assert compute_transaction_id(changed_nonce) != original_tx_id
    assert compute_transaction_id(changed_signature) != original_tx_id


def test_tx_id_ignores_local_only_fields():
    payload = _signed_transaction_payload()
    original_tx_id = compute_transaction_id(payload)

    changed_status = dict(payload, status="mempool")
    changed_created_at = dict(payload, created_at="2026-07-16T00:00:00+00:00")

    assert compute_transaction_id(changed_status) == original_tx_id
    assert compute_transaction_id(changed_created_at) == original_tx_id


def test_tx_id_is_lowercase_sha256_hex():
    tx_id = compute_transaction_id(_signed_transaction_payload())
    assert len(tx_id) == 64
    assert tx_id == tx_id.lower()
    assert all(ch in "0123456789abcdef" for ch in tx_id)


def test_canonical_transaction_serialization_is_stable_and_excludes_local_fields():
    payload = _signed_transaction_payload(
        from_address=Account.create().address.upper().replace("0X", "0x"),
        to_address=Account.create().address.upper().replace("0X", "0x"),
        amount="1.5000",
        fee="0.000000",
        created_at="2026-07-20T00:00:00+00:00",
        updated_at="2026-07-20T00:00:00+00:00",
        status="failed",
    )

    canonical = canonicalize_transaction_payload(payload)

    assert canonical == canonicalize_transaction_payload(dict(payload, created_at="2026-07-21T00:00:00+00:00"))
    assert '"amount":"1.5"' in canonical
    assert '"fee":"0"' in canonical
    assert '"from_address":"' + normalize_wallet_address(payload["from_address"]) + '"' in canonical
    assert '"to_address":"' + normalize_wallet_address(payload["to_address"]) + '"' in canonical
    assert "created_at" not in canonical
    assert "updated_at" not in canonical
    assert "status" not in canonical


def test_build_native_transaction_generates_valid_deterministic_tx_id():
    payload = _signed_transaction_payload()
    transaction = build_native_transaction(
        network=payload["network"],
        from_address=payload["from_address"],
        to_address=payload["to_address"],
        amount=payload["amount"],
        fee=payload["fee"],
        nonce=payload["nonce"],
        memo=payload["memo"],
        timestamp=payload["timestamp"],
        signature=payload["signature"],
        signature_scheme=payload["signature_scheme"],
        signed_message=payload["signed_message"],
        signed_message_hash=payload["signed_message_hash"],
        status=payload["status"],
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )

    assert transaction.tx_id == compute_transaction_id(payload)
