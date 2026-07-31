# Native Transaction Layer Plan

As of Friday, July 31, 2026, Task 8.6 is the current implemented phase of the native transaction layer.

## Current Scope

Task 8.6 adds meme-block inclusion and settlement for valid native ZOID transfers on top of the Task 8.5 peer gossip and local mempool layer.

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
- pending outgoing balance reservation
- pending incoming balance display
- available-balance enforcement on signed transfer submission
- native account balance endpoint
- local mempool validation
- local mempool admission endpoint
- local mempool read endpoints
- local mempool revalidation endpoint
- peer transaction receive endpoint
- transaction broadcast endpoint
- peer transaction fetch endpoint
- peer mempool summary endpoint
- lightweight peer transaction and mempool sync helpers
- deterministic native transaction selection for meme-mined blocks
- native transaction settlement on accepted block persistence
- settled balance mutation from accepted chain blocks
- mempool cleanup after block inclusion

Not implemented yet:

- replacement policy
- full mempool consensus
- deep peer block validation hardening
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
- the transaction reduces available balance
- final balance does not change yet

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
  "message": "Signed native ZOID transaction recorded. It is not settled until included in a meme-mined block."
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

Task 8.3 also enforces:

- amount plus fee must be less than or equal to available balance
- insufficient submissions are rejected before transaction record acceptance
- insufficient submissions do not reserve nonce
- insufficient submissions do not change balance state

## Balance Model

Task 8.3 balance fields:

- `final_balance`: chain-derived native balance only
- `pending_outgoing`: accepted outgoing non-final native transfers, including `amount + fee`
- `pending_incoming`: accepted incoming non-final native transfers, display only
- `available_balance = final_balance - pending_outgoing`
- `native_balance`: compatibility field equal to `final_balance` for now

Statuses that reserve funds:

- `signed_pending`
- `validated_pending`
- `mempool`

Statuses that do not reserve funds:

- `rejected`
- `failed`
- `expired`
- `included`
- `settled`

Current fee policy:

- fee field exists for forward compatibility
- nonzero fees are not enabled yet
- sufficiency math still uses `amount + fee`

Current read surfaces:

- `GET /accounts/{wallet_address}`
- `GET /accounts/{wallet_address}/balance`
- compatibility: `GET /wallets/{wallet_address}/balance`

## Local Mempool Lifecycle

Task 8.4 uses these non-final statuses:

- `signed_pending`: recorded but not yet admitted
- `validated_pending`: optional intermediate eligible state
- `mempool`: admitted to the local mempool
- `rejected`: failed validation
- `expired`: expired before inclusion

Task 8.4 rules:

- only `mempool` or `validated_pending` transactions are future block-inclusion candidates
- `signed_pending` alone is not enough for block inclusion
- mempool transactions remain non-final until block inclusion
- final balances change only after accepted chain settlement

Validation checks used for local mempool admission:

- canonical transaction shape
- deterministic `tx_id`
- network match
- signed message match
- signature recovery
- nonce policy
- available-balance sufficiency
- zero-fee policy
- eligible status

Storage approach:

- `NativeTransaction` remains the canonical source of truth
- `status = mempool` means the transaction is in the local mempool
- no separate duplicate mempool storage copy is required

Endpoints:

- `POST /transactions/{tx_id}/admit`
- `GET /mempool`
- `GET /mempool/{tx_id}`
- `POST /mempool/revalidate`

Ordering policy:

- `admitted_at` ascending
- then `from_address` ascending
- then `nonce` ascending
- then `tx_id` ascending

## Peer Transaction Gossip

Task 8.5 and 8.6 architecture:

- user transaction signatures authorize the transfer itself
- peer auth or signed peer messages authorize node-to-node transport
- peer-received transactions do not require local wallet sessions
- local nodes validate peer transactions independently before mempool admission
- mempools remain local and are not consensus-critical yet

Peer endpoints:

- `POST /peers/transactions/receive`
- `GET /peers/transactions/{tx_id}`
- `GET /peers/mempool/summary`
- `POST /transactions/{tx_id}/broadcast`

Sync helpers:

- `sync_transaction_from_peer(...)`
- `sync_mempool_from_peer(...)`

Trust rules:

- do not trust peer-provided local status blindly
- do not trust peer local-only fields such as `admitted_at`, `created_at`, `updated_at`, or `rejection_reason`
- canonical payload, `tx_id`, signed message, and signature remain authoritative
- local validation may reject transactions another peer accepted

Auto-broadcast decision:

- automatic gossip on local mempool admission remains disabled for now
- accepted meme-mined blocks may include up to `MAX_TRANSACTIONS_PER_BLOCK` native transfers
- transaction ordering is deterministic and block-local validation runs again at mint time
- transfers do not create blocks by themselves and only ride inside certified meme-mined blocks
- settled transactions are marked with `status = settled`, `included_block_hash`, `included_block_height`, and `settled_at`
- final balances are derived from accepted chain blocks, including settled incoming and outgoing native transfers
- manual broadcast is available through `POST /transactions/{tx_id}/broadcast`

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
- a recorded transaction is not the same thing as a settled transfer until it is included in an accepted meme-mined block

## Next Planned Steps

- Task 8.7 hardens full block-with-transaction validation and peer compatibility
