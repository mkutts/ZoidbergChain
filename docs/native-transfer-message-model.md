# Native Transfer Message Model

Task 7.7 defines the native ZOID transfer message model only.

- Task 7.8 implements MetaMask-signed transfer submission.
- Task 8 hardens balances, nonces, replay protection, mempool behavior, fees, and block inclusion.
- This task does not execute transfers, mutate balances, or include transfers in blocks.

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

## Signature Verification Role

Task 7.7 adds reusable signature verification helpers for future transfer submission work.

- Verification uses the same Ethereum `personal_sign` recovery approach as wallet login, signed submissions, and signed votes.
- The helper only proves signer consistency with `from_address`.
- The helper does not mutate balances.
- The helper does not mark a transfer final.
- The helper does not replace future nonce, balance, replay, or mempool checks.

## Transfer Status Model

The future transfer lifecycle statuses are:

- `draft`
- `signed`
- `pending`
- `rejected`
- `included`
- `failed`

Task 7.7 defines these statuses for future use only. It does not implement a live mempool or block inclusion flow yet.

## Deferred Work

Deferred to Task 7.8:

- signed transfer submission endpoint or handler
- verified-session coupling for live transfer requests
- transfer draft or pending persistence behavior

Deferred to Task 8:

- balance sufficiency checks
- strict nonce sequencing and replay protection
- fee policy hardening
- mempool behavior
- block inclusion
- final denomination and smallest-unit policy
