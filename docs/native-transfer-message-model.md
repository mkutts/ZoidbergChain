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
- `GET /accounts/{wallet_address}/transactions` and `GET /wallets/{wallet_address}/transactions` expose transaction history with incoming/outgoing direction.
- Pending transfer intents do not mutate native balances yet.
- Peer propagation, mempool behavior, replay hardening, balance settlement, and block inclusion remain deferred to Task 8.
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
- `nonce`: Required now as part of the signed payload, with stricter enforcement deferred.
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
2. The backend validates the verified `from_address`, normalizes fields, generates a single-use expiring nonce, and returns the exact signing message.
3. MetaMask signs that exact backend message with `personal_sign`.
4. The client submits the signed payload to `POST /transfers/submit`.
5. The backend verifies:
   - verified session ownership
   - signer recovery matches `from_address`
   - request fields still match the stored challenge
   - nonce is still active and unused
6. The backend stores a non-final transfer intent record with status `signed_pending`.
7. The backend also stores a canonical `NativeTransaction` record with the same `signed_pending` status and deterministic `tx_id`.

Signed pending means:

- the transfer intent was signed and accepted for future processing
- the transaction record was created and assigned a deterministic `tx_id`
- balances are not reduced yet
- no mempool or block inclusion happens yet
- no ERC-20 transfer has happened

Task 7.9 clarifies the next future states after `signed_pending`:

- `validated_pending`
- `mempool`
- `included`
- `settled`

Those states are planned but not implemented in Task 7.8.

## Transfer Status Model

The future transfer lifecycle statuses are:

- `draft`
- `signed`
- `signed_pending`
- `pending`
- `rejected`
- `included`
- `failed`

Task 7.7 defines these statuses for future use only. It does not implement a live mempool or block inclusion flow yet.

## Deferred Work

Deferred to Task 7.8:

- none; Task 7.8 implements the initial signed pending intent submission path

Deferred to Task 8:

- strict nonce sequencing and replay protection in Task 8.2
- balance sufficiency checks in Task 8.3
- fee policy hardening
- mempool behavior
- block inclusion
- final denomination and smallest-unit policy
- transaction id generation
- peer transaction gossip
