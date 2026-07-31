# Native Transaction Layer Plan

As of July 30, 2026, Task 8.2 is the current implemented phase of the native transaction layer.

## Current Scope

Task 8.2 adds nonce tracking and replay protection on top of the Task 8.1 canonical transaction record.

Implemented now:

- canonical `NativeTransaction` storage
- deterministic `tx_id` generation
- canonical transaction serialization
- conversion of signed transfer intents into stored transaction records
- read-only transaction lookup by `tx_id`
- account transaction history by native `0x` address
- JSON and SQLite persistence
- light transaction-shape validation
- strict sequential nonce tracking
- replay protection and duplicate idempotency
- nonce read endpoint

Not implemented yet:

- balance sufficiency enforcement
- mempool validation or admission requirements
- peer transaction gossip
- block inclusion
- settlement
- balance mutation from transfer records
- wrapped ZOID or ERC-20 behavior

## Canonical NativeTransaction Shape

Task 8.1 stores these fields:

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

Current rules:

- `transaction_type` is `native_transfer`
- `network` must match the active ZoidbergChain network name
- addresses are normalized lowercase Ethereum-style `0x` addresses
- `amount` and `fee` use decimal-safe string handling
- current fee policy remains zero-only in practice

## Transaction Statuses

Supported statuses:

- `signed_pending`
- `validated_pending`
- `mempool`
- `included`
- `settled`
- `rejected`
- `failed`
- `expired`

Task 8.2 actively uses `signed_pending` for newly recorded transactions.

Meaning of `signed_pending`:

- the signed transaction was accepted and recorded
- the transaction has a deterministic `tx_id`
- the transaction can be queried by `GET /transactions/{tx_id}`
- the transaction is not settled
- the transaction reserves its sender nonce
- balances do not change yet

## Deterministic tx_id Rule

Task 8.1 computes:

`tx_id = SHA-256(canonical signed transaction payload)`

Included in `tx_id` hashing:

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

Excluded from `tx_id` hashing:

- `status`
- `created_at`
- `updated_at`
- `included_block_hash`
- `included_block_height`
- `settled_at`
- `rejection_reason`

Rules:

- the same signed payload always produces the same `tx_id`
- changing sender, recipient, amount, nonce, or signature changes `tx_id`
- `tx_id` is lowercase SHA-256 hex

## Canonical Serialization

Task 8.1 canonical serialization uses:

- stable key ordering
- normalized lowercase `0x` addresses
- stable decimal-safe amount and fee formatting
- no Python object representation
- only the signed transaction timestamp, not local node timestamps

This canonical string is the hash input for `tx_id`.

## Nonce Policy

Task 8.2 nonce rules:

- nonce is per `from_address`
- initial nonce is `1`
- nonce is included in the signed transfer message
- nonce is part of the canonical transaction payload
- nonce is part of `tx_id` computation
- no gap nonces are allowed
- strict sequential nonce order is active
- no replacement policy exists yet

Statuses that reserve nonce:

- `signed_pending`
- `validated_pending`
- `mempool`

Statuses that permanently consume nonce:

- `included`
- `settled`

Statuses that do not reserve nonce:

- `rejected`
- `failed`
- `expired`

Exact duplicate behavior:

- the same signed transaction returns the existing record idempotently
- the same sender plus same nonce plus different `tx_id` is rejected

Nonce read surface:

- `GET /accounts/{wallet_address}/nonce`

## Submit-Time Behavior

`POST /transfers/submit` now records:

- a local `transfer_id`
- a canonical `tx_id`
- a `signed_pending` transaction record

Returned response:

```json
{
  "tx_id": "...",
  "transfer_id": "...",
  "status": "signed_pending",
  "message": "Signed native ZOID transaction recorded. It is not settled until transaction processing is enabled."
}
```

Identifier meaning:

- `transfer_id` is a local record identifier
- `tx_id` is the deterministic network transaction identifier

Task 8.2 also enforces:

- the challenge uses the backend-derived expected nonce
- exact duplicate signed submission returns the existing record
- conflicting same-sender same-nonce submission is rejected
- accepted `signed_pending` records reserve nonce across restart

## Read APIs

Task 8.1 read surfaces:

- `GET /transactions/{tx_id}`
- `GET /accounts/{wallet_address}/transactions`
- compatibility: `GET /wallets/{wallet_address}/transactions`

History results distinguish:

- `outgoing`
- `incoming`

These endpoints are read-only and do not expose private keys, session tokens, storage paths, or stack traces.

## Account Model Reminder

Native accounts are MetaMask/Ethereum-style `0x` ZoidbergChain accounts.

- old development wallets are not the native account registry
- native transfer records do not change balances yet
- a recorded transaction is not the same thing as a settled transfer

## Next Planned Steps

- Task 8.3 adds balance sufficiency enforcement
