# Native Transfer Message Model

As of Saturday, August 1, 2026, Task 8.10 has completed a security and validation pass over signed native transfer intents, canonical transaction storage, mempool handling, peer gossip, block settlement, and wallet wording.

## Purpose

Native ZOID transfers are ZoidbergChain-native messages, not Ethereum or ERC-20 token transfers.

- MetaMask is used for signing
- the `0x...` address is the native ZoidbergChain account identifier
- signing a transfer message alone does not settle the transfer

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

In Task 8.3, `signed_pending` also reserves the sender nonce and reduces available balance.

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

## Nonce Policy

Task 8.2 rules:

- nonce starts at `1`
- nonce is per `from_address`
- nonce is included in the signed transfer message
- strict sequential sender nonces are enforced
- exact duplicate signed transaction is idempotent
- same sender plus same nonce plus different `tx_id` is rejected

Read endpoint:

- `GET /accounts/{wallet_address}/nonce`

## Balance Policy

Task 8.3 rules:

- `final_balance` is chain-derived only
- `pending_outgoing` includes accepted outgoing non-final transfers and uses `amount + fee`
- `pending_incoming` is display-only and does not increase available balance
- `available_balance = final_balance - pending_outgoing`
- accepted `signed_pending` transfers reduce available balance
- final balance changes only after the transaction is included in an accepted meme-mined block
- nonzero fees are not enabled yet

## Local Mempool Policy

Task 8.4 adds:

- local mempool admission from `signed_pending`
- local mempool validation using canonical transaction rules
- local mempool revalidation
- deterministic local ordering

Current statuses:

- `signed_pending`
- `validated_pending`
- `mempool`
- `rejected`
- `expired`

Current mempool endpoints:

- `POST /transactions/{tx_id}/admit`
- `GET /mempool`
- `GET /mempool/{tx_id}`
- `POST /mempool/revalidate`

Mempool transactions remain non-final until included in a meme-mined block.

## Peer Gossip Policy

Task 8.5 adds:

- peer transaction receive at `POST /peers/transactions/receive`
- peer transaction fetch at `GET /peers/transactions/{tx_id}`
- peer mempool summary at `GET /peers/mempool/summary`
- manual transaction broadcast at `POST /transactions/{tx_id}/broadcast`
- lightweight peer mempool sync helpers

Current rules:

- peer transport auth is separate from the user transaction signature
- peer-received transactions do not require local wallet sessions
- local validation may reject a peer transaction that another node accepted
- mempools are local candidate pools and are not consensus-critical yet
- no automatic broadcast is required for this phase

## Block Inclusion And Settlement

Task 8.6 and 8.7 add:

- deterministic transaction selection from the local mempool during certified meme minting
- block-native transaction fields: `native_transactions`, `transaction_ids`, `transaction_count`, and `transactions_hash`
- settlement to `status = settled` immediately after accepted local or peer block persistence
- `included_block_hash`, `included_block_height`, and `settled_at` tracking
- chain-before-block validation for native transfer signatures, balances, nonces, and duplicate settlement
- canonical block ordering by `from_address`, then `nonce`, then `tx_id`

Current rules:

- transfers do not create blocks by themselves
- transfers may only ride inside certified meme-mined blocks
- local nodes revalidate tx shape, signature, network, nonce, and available balance at block construction time
- peer-received blocks are validated from accepted chain state rather than local mempool assumptions
- transaction ordering is deterministic and does not use fee priority
- included transactions are removed from the local mempool
- settled transfers change final balances through accepted chain state

## Submit And Read Flow

Current flow:

1. The client requests a transfer-signing challenge.
2. The wallet signs the exact backend-built message.
3. The client submits the signed payload to `POST /transfers/submit`.
4. The backend stores a local transfer intent record.
5. The backend stores a canonical `NativeTransaction` record with deterministic `tx_id`.
6. The accepted `signed_pending` record reserves the sender nonce.
7. Storage reload revalidates canonical native transaction records before they can reserve nonce or balance again.

The submit response now includes both identifiers:

- `transfer_id` for the local record
- `tx_id` for the deterministic transaction identifier

Read endpoints:

- `GET /transfers/{transfer_id}`
- `GET /transactions/{tx_id}`
- `GET /accounts/{wallet_address}/transactions`
- compatibility: `GET /wallets/{wallet_address}/transactions`

Canonical UX rules:

- `/accounts/{wallet_address}/transactions` is the primary history surface
- `/wallets/{wallet_address}/transactions` remains a compatibility read
- native ZOID wording must not describe these records as Ethereum or ERC-20 transfers
- preferred lifecycle wording is:
- `Signed native ZOID transfer recorded. Not settled yet.`
- `In local mempool. Not settled yet.`
- `Included in meme-mined block.`
- `Settled on ZoidbergChain.`

## Important Current Limits

Current limits:
- create transfer-only blocks
- support replacement policy
- provide full mempool consensus across peers
- support wrapped ZOID or ERC-20 behavior
- no external production security audit exists yet
- the current hardening target remains controlled dev/testnet use
