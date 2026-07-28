# Native Transfer Message Model

Task 7.7 defines the native ZOID transfer message model only.

- Task 7.8 implements MetaMask-signed transfer submission.
- Task 8 hardens balances, nonces, replay protection, mempool behavior, fees, and block inclusion.
- This task does not execute transfers, mutate balances, or include transfers in blocks.

Task 8.1 extends that model further into canonical signed native transaction records.

- `POST /auth/wallet/transfer-challenge` issues the exact backend-built message for MetaMask signing.
- `POST /transfers/submit` stores a signed transfer intent and a canonical non-final `NativeTransaction` record.
- `GET /transfers/{transfer_id}` and `GET /wallets/{wallet_address}/transfers` expose safe read-only transfer intent history and include `tx_id` when available.
- `GET /transactions/{tx_id}` exposes the safe canonical transaction view.
- `GET /accounts/{wallet_address}/nonce` exposes the current strict-sequential nonce state.
- `GET /accounts/{wallet_address}/transactions` and `GET /wallets/{wallet_address}/transactions` expose transaction history with incoming/outgoing direction.
- Pending transfer intents do not mutate native balances yet.
- Peer propagation is implemented by Task 8.5.
- Balance settlement and block inclusion are implemented by Task 8.6.
- Task 8.7 hardens block validation, peer receive, and chain sync for transfer-bearing meme blocks.
- Task 7.9 defines the design path from transfer intents to settled native transactions in [docs/native-transaction-layer-plan.md](C:/Users/mattk/ZoidbergChain/docs/native-transaction-layer-plan.md).

## Purpose

Native ZOID transfers are ZoidbergChain-native messages, not Ethereum or ERC-20 token transfers.

- MetaMask is used only as the signing wallet for the native account address.
- The `0x...` address is still the native ZoidbergChain account identifier.
- Transfer execution remains deferred until the later submission and validation tasks.

## Canonical Transfer Payload

Canonical payload shape:

```json
{
  "action": "transfer_zoid",
  "network": "zoidberg-testnet-1",
  "from_address": "0x...",
  "to_address": "0x...",
  "amount": "10",
  "nonce": 1,
  "fee": "0",
  "timestamp": "2026-07-15T15:30:00+00:00",
  "memo": "optional"
}
```

Field meaning:

- `action`: Must be exactly `transfer_zoid`.
- `network`: Must match the active ZoidbergChain network name.
- `from_address`: The signing and sending native ZoidbergChain wallet address.
- `to_address`: The receiving native ZoidbergChain wallet address.
- `amount`: The native ZOID amount as a decimal-safe string.
- `nonce`: Required as part of the signed payload, with Task 8.2 enforcing strict sequential sender nonces beginning at `1`.
- `fee`: The transfer fee placeholder as a decimal-safe string. It is modeled now but not enforced for live transfer execution yet.
- `timestamp`: ISO 8601 timestamp with timezone.
- `memo`: Optional user-facing note with a bounded length.

Validation rules:

- `from_address` and `to_address` must normalize to lowercase Ethereum-style `0x` addresses.
- `from_address` cannot equal `to_address`.
- `amount` must be positive.
- `fee` must be zero or positive.
- `nonce` must be present and must be an integer.
- `timestamp` must be a timezone-aware ISO 8601 value.
- `memo` is optional and currently limited to 280 characters.

## Decimal Amount Strategy

Task 7.7 uses decimal-safe parsing and avoids Python floating point for native ZOID amounts.

- Accepted examples: `"1"`, `"1.5"`, `"0.000001"`
- Rejected examples: `"0"`, `"-1"`, `"abc"`, `NaN`, `Infinity`
- Scientific notation such as `"1e-6"` is rejected to keep serialization stable and human-reviewable.

Current provisional precision rule:

- Native ZOID transfer messages currently allow up to 6 decimal places.
- This is a temporary message-model rule to avoid float precision issues before final denomination hardening.
- Final smallest-unit policy and denomination hardening are deferred to Task 8.

## Canonical Signing Message

MetaMask `personal_sign` is used for the first native transfer-signing phase.

Canonical signing message shape:

```text
ZoidbergChain Native Transfer

Action: transfer_zoid
Network: zoidberg-testnet-1
From: 0x...
To: 0x...
Amount: 10
Fee: 0
Nonce: 1
Timestamp: 2026-07-15T15:30:00+00:00
Memo: optional

This authorizes a native ZOID transfer on ZoidbergChain.
This is not an Ethereum/ERC-20 transfer.
```

Signing rules:

- The message must remain deterministic for the same canonical payload.
- The backend later verifies that the recovered signer matches `from_address`.
- The signature does not by itself execute or finalize a transfer in Task 7.7.

## Canonical NativeTransaction Record

Task 8.1 adds a canonical `NativeTransaction` record with:

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
- `admitted_at`
- `included_block_hash`
- `included_block_height`
- `settled_at`
- `rejection_reason`

Current `transaction_type` is always `native_transfer`.

Current status values are:

- `signed_pending`
- `validated_pending`
- `mempool`
- `included`
- `settled`
- `rejected`
- `failed`
- `expired`

## Transaction ID Rule

Task 8.1 computes:

`tx_id = SHA-256(canonical signed transaction payload)`

Included in canonical hashing:

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

Excluded from canonical hashing:

- `status`
- `created_at`
- `updated_at`
- `admitted_at`
- `included_block_hash`
- `included_block_height`
- `settled_at`
- `rejection_reason`

The canonical serialization uses:

- stable key ordering
- normalized lowercase `0x` addresses
- decimal-safe normalized amount and fee strings
- timezone-aware ISO 8601 timestamps
- no Python object representation

## Task 8.2 Nonce Enforcement

Current rules:

- nonce is per `from_address`
- first accepted nonce is `1`
- backend transfer challenge assigns the expected next nonce
- frontend signs the backend-provided nonce
- exact duplicate signed transaction returns the existing recorded transaction
- conflicting duplicate nonce is rejected
- `signed_pending` records reserve nonce immediately
- Task 8.3 now enforces available-balance sufficiency at submit time

Current public nonce endpoint:

```json
{
  "wallet_address": "0x...",
  "next_nonce": 2,
  "used_nonces": [1],
  "reserved_nonces": [1],
  "policy": "strict_sequential"
}
```

## Task 8.3 Balance Sufficiency

Current native balance fields:

- `final_balance`
- `pending_outgoing`
- `pending_incoming`
- `available_balance`
- backward-compatible `native_balance`, which currently equals `final_balance`

Current rules:

- `pending_outgoing` includes accepted non-final outgoing `amount + fee`
- `pending_incoming` shows non-final incoming amount only
- `pending_incoming` does not increase `available_balance`
- submit-time acceptance requires `amount + fee <= available_balance`
- insufficient transfers are rejected before transaction record acceptance
- insufficient transfers do not reserve funds
- nonzero fees are not enabled yet
- signed pending transfers are still not settled
- `signed_pending`, `validated_pending`, and `mempool` all reserve available balance today

Task 8.4 now adds mempool storage and validation.

Task 8.6 adds block inclusion and settlement.

Current Task 8.6 block-inclusion behavior:

- only canonical signed transfer fields are embedded in blocks
- local lifecycle fields such as `created_at`, `updated_at`, `admitted_at`, `included_block_hash`, `included_block_height`, `settled_at`, and `rejection_reason` remain node-derived state and are not part of the block snapshot
- block snapshots are validated by reconstructing the canonical signed transaction payload and verifying signature integrity

Current Task 8.7 block-validation behavior:

- a native transfer snapshot inside a block is validated from the chain state before that block, not from local mempool assumptions
- block snapshots must have matching `transaction_count`, ordered `transaction_ids`, and `transactions_hash`
- duplicate `tx_id`, already-settled `tx_id`, wrong network, invalid signature, unsupported type, nonce gap, duplicate nonce, lower-than-expected nonce, overspend, and nonzero fee all reject the block
- transfer-bearing blocks must still be certified meme-mined blocks; transfer-only blocks are invalid
- peer-provided status is not authoritative for block validation; `tx_id`, signed payload, and signature remain authoritative

## Signature Verification Role

Task 7.7 adds reusable signature verification helpers for future transfer submission work.

- Verification uses the same Ethereum `personal_sign` recovery approach as wallet login, signed submissions, and signed votes.
- The helper only proves signer consistency with `from_address`.
- The helper does not mutate balances.
- The helper does not mark a transfer final.
- The helper does not replace future nonce, balance, replay, or mempool checks.

## Task 7.8 Pending Submission Flow

Task 7.8 turns the transfer model into a signed pending intent flow, not a final settlement flow.

1. A verified MetaMask wallet requests `POST /auth/wallet/transfer-challenge`.
2. The backend validates the verified `from_address`, derives the expected next persisted transaction nonce, and returns the exact signing message with that nonce.
3. MetaMask signs that exact backend message with `personal_sign`.
4. The client submits the signed payload to `POST /transfers/submit`.
5. The backend verifies:
   - verified session ownership
   - signer recovery matches `from_address`
   - request fields still match the stored challenge
   - nonce is still active and unused
6. The backend stores a non-final transfer intent record with status `signed_pending`.
7. The backend also stores a canonical `NativeTransaction` record with the same `signed_pending` status and deterministic `tx_id`.
8. The transaction may later move into local `mempool` through `POST /transactions/{tx_id}/admit` or optional `admit_to_mempool=true` on submit.

Signed pending means:

- the transfer intent was signed and accepted for future processing
- the transaction record was created and assigned a deterministic `tx_id`
- the accepted `signed_pending` record now reserves its nonce
- pending outgoing now reduces available balance, but final balance is not reduced yet
- local mempool admission is now available, but no peer gossip or block inclusion happens yet
- no ERC-20 transfer has happened

Task 7.9 clarifies the next future states after `signed_pending`:

- `validated_pending`
- `mempool`
- `included`
- `settled`

Those states are now partially implemented by Task 8.4 and completed for local block settlement by Task 8.6.

## Transfer Status Model

The future transfer lifecycle statuses are:

- `draft`
- `signed`
- `signed_pending`
- `pending`
- `rejected`
- `included`
- `failed`

Task 8.4 now implements the local `signed_pending -> mempool` path, mempool revalidation, and safe mempool read endpoints.

## Deferred Work

Deferred to Task 7.8:

- none; Task 7.8 implements the initial signed pending intent submission path

Deferred to Task 8:

- fee policy hardening
- final denomination and smallest-unit policy

Implemented by Task 8.5:

- peer transaction gossip

Implemented by Task 8.6:

- deterministic inclusion of validated native transfers in meme-mined blocks
- block-native transaction metadata fields `native_transactions`, `transaction_ids`, `transaction_count`, and `transactions_hash`
- immediate local settlement when an accepted block includes a transfer
- peer block settlement for matching local mempool transfers

Implemented by Task 8.7:

- chain-before-block validation for transfer-bearing blocks
- structured block rejection reasons for native transfer validation and reward validation
- hardened peer block receive so invalid transfer-bearing blocks do not mutate balances or local transaction status
- hardened chain sync so accepted transfer-bearing blocks reconstruct and reconcile settled transaction state deterministically

Implemented by Task 8.4:

- local mempool validation
- local mempool admission
- local mempool revalidation
- deterministic ordering by `admitted_at`, then nonce, then `tx_id`

Implemented by Task 8.5:

- peer transaction receive at `POST /peers/transactions/receive`
- peer transaction fetch at `GET /peers/transactions/{tx_id}`
- peer mempool summary at `GET /peers/mempool/summary`
- manual peer broadcast at `POST /transactions/{tx_id}/broadcast`
- transaction gossip uses peer transport auth separately from the signed user transaction payload
- peer-received transactions do not require local wallet sessions
- local mempool validation remains authoritative and may reject a transaction another peer accepted
