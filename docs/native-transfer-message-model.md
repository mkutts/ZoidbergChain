# Native Transfer Message Model

As of July 30, 2026, signed native transfer intents exist and Task 8.1 records them as canonical non-final native transactions.

## Purpose

Native ZOID transfers are ZoidbergChain-native messages, not Ethereum or ERC-20 token transfers.

- MetaMask is used for signing
- the `0x...` address is the native ZoidbergChain account identifier
- signing a transfer message does not settle the transfer

## Canonical Signed Transfer Payload

```json
{
  "action": "transfer_zoid",
  "network": "zoidberg-testnet",
  "from_address": "0x...",
  "to_address": "0x...",
  "amount": "10",
  "nonce": "1",
  "fee": "0",
  "timestamp": "2026-07-30T12:00:00+00:00",
  "memo": "optional"
}
```

Rules:

- `action` must be `transfer_zoid`
- `network` must match the active network name
- `from_address` and `to_address` must be normalized lowercase `0x` addresses
- sender and recipient must differ
- `amount` must be positive
- `fee` must be zero or nonnegative
- `nonce` must be present
- `timestamp` must be ISO 8601 with timezone
- `memo` is optional

## Signing Message

MetaMask `personal_sign` is used for the current native transfer-signing flow.

Canonical message shape:

```text
ZoidbergChain Native Transfer

Action: transfer_zoid
Network: zoidberg-testnet
From: 0x...
To: 0x...
Amount: 10
Fee: 0
Nonce: 1
Timestamp: 2026-07-30T12:00:00+00:00
Memo: optional

This authorizes a native ZOID transfer on ZoidbergChain.
This is not an Ethereum/ERC-20 transfer.
```

The same logical transfer payload must always produce the same signing message.

## Canonical NativeTransaction Record

Task 8.1 stores each successful signed transfer submission as a canonical `NativeTransaction`.

Fields:

- `tx_id`
- `transaction_type`
- `network`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `memo`
- `timestamp`
- `signature`
- `signature_scheme`
- `signed_message`
- `signed_message_hash`
- `status`
- `created_at`
- `updated_at`
- `included_block_hash`
- `included_block_height`
- `settled_at`
- `rejection_reason`

Current `transaction_type` is always `native_transfer`.

Supported statuses:

- `signed_pending`
- `validated_pending`
- `mempool`
- `included`
- `settled`
- `rejected`
- `failed`
- `expired`

Current submit-time status is `signed_pending`.

## tx_id Computation

Task 8.1 computes:

`tx_id = SHA-256(canonical signed transaction payload)`

Included fields:

- `transaction_type`
- `network`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `memo`
- `timestamp`
- `signature`
- `signature_scheme`
- `signed_message`
- `signed_message_hash`

Excluded local-only fields:

- `status`
- `created_at`
- `updated_at`
- `included_block_hash`
- `included_block_height`
- `settled_at`
- `rejection_reason`

## Canonical Serialization Rules

Task 8.1 canonical serialization uses:

- stable key ordering
- stable decimal-safe formatting
- normalized addresses
- no Python object repr
- no local-only timestamps in the hash input

## Submit And Read Flow

Current flow:

1. The client requests a transfer-signing challenge.
2. The wallet signs the exact backend-built message.
3. The client submits the signed payload to `POST /transfers/submit`.
4. The backend stores a local transfer intent record.
5. The backend stores a canonical `NativeTransaction` record with deterministic `tx_id`.

The submit response now includes both identifiers:

- `transfer_id` for the local record
- `tx_id` for the deterministic transaction identifier

Read endpoints:

- `GET /transfers/{transfer_id}`
- `GET /transactions/{tx_id}`
- `GET /accounts/{wallet_address}/transactions`
- compatibility: `GET /wallets/{wallet_address}/transactions`

## Important Current Limits

Task 8.1 does not yet:

- enforce nonce sequencing
- enforce balance sufficiency
- admit transactions to a mempool as part of normal submit flow
- gossip transactions to peers
- include transactions in blocks
- settle transfers
- mutate balances from transfer records

Balances stay unchanged until later transaction-processing tasks.

## Next Planned Steps

- Task 8.2 adds nonce tracking and replay protection
- Task 8.3 adds balance sufficiency enforcement
