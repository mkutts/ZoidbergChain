# Native Account Model

As of Saturday, August 1, 2026, MetaMask-backed `0x...` addresses are the canonical native ZoidbergChain account identity, and Task 8.10 hardens wallet balances, transfer history wording, persistence safety, and the native account UX for controlled dev/testnet use.

## Current Status

Current status:

- ZoidbergChain is complete through Task 8 for controlled dev/testnet use
- MetaMask-backed native accounts use canonical native transaction records
- old `/wallets/...` endpoints remain read-only compatibility surfaces
- the current roadmap moves next to Task 9 public demo and testnet deployment readiness
- later stages are documented in [roadmap.md](/C:/Users/mattk/ZoidbergChain/docs/roadmap.md)

## Core Model

- a verified MetaMask signer becomes a native ZoidbergChain account
- the account identifier is the normalized lowercase `0x...` address
- native ZOID balances live in ZoidbergChain state
- old generated server wallets remain development-only compatibility tools

No pre-registration step in the old dev-wallet list is required.

## What A Native Account Can Own

A native account may accumulate:

- signed meme submissions
- signed originality votes
- native ZOID meme-mining rewards
- signed transfer intents
- canonical native transaction records with deterministic `tx_id`

## Read APIs

Primary read endpoints:

- `GET /accounts/{wallet_address}`
- `GET /accounts/{wallet_address}/submissions`
- `GET /accounts/{wallet_address}/votes`
- `GET /accounts/{wallet_address}/rewards`
- `GET /accounts/{wallet_address}/transfers`
- `GET /accounts/{wallet_address}/transactions`
- `GET /accounts/{wallet_address}/balance`
- `GET /mempool`

Compatibility read endpoints:

- `GET /wallets/{wallet_address}/transfers`
- `GET /wallets/{wallet_address}/transactions`
- `GET /wallets/{wallet_address}/balance`

These endpoints:

- require an Ethereum-style `0x...` address for native account reads
- normalize addresses consistently
- expose safe read-only fields
- do not require the account to appear in the development wallet registry
- treat `/accounts/...` as the canonical native account surface
- keep `/wallets/...` reads as legacy compatibility endpoints for now

## Task 8.1 Transaction Recording

Task 8.1 records each successful signed native transfer submission in two related forms:

- `transfer_id`: local transfer-intent identifier
- `tx_id`: deterministic canonical transaction identifier

Current meaning of `signed_pending`:

- the signed transaction record exists
- the transaction can be queried
- it is not settled
- it reserves the sender nonce
- it reduces available balance
- it does not change final balance yet

Task 8.3 account rules:

- balances are chain-derived only
- pending outgoing transfers reduce available balance
- pending incoming transfers do not increase available balance
- non-final transfer records do not mutate final balances by themselves
- transaction history may show outgoing and incoming signed records
- native accounts remain MetaMask/Ethereum-style `0x` ZoidbergChain accounts
- old development wallets are not the native account registry

Task 8.2 nonce rules:

- nonce is per `from_address`
- nonce starts at `1`
- strict sequential nonce policy is active
- exact duplicate signed transaction returns the existing record
- conflicting same-sender same-nonce transaction is rejected
- `GET /accounts/{wallet_address}/nonce` exposes `next_nonce`, `used_nonces`, `reserved_nonces`, policy, and initial nonce

Task 8.4 mempool rules:

- signed pending transactions may be admitted into the local mempool
- mempool transactions remain non-final
- mempool transactions still reserve nonce and available balance
- local mempool ordering is deterministic
- mempool transactions remain non-final until accepted block inclusion

Task 8.5 peer rules:

- peer-received transactions do not require local wallet sessions
- peer transport auth is separate from user transaction signatures
- local nodes may reject peer transactions during local validation
- peer mempools are not consensus-critical

Task 8.6 settlement rules:

- certified meme-mined blocks may include native transactions from the local mempool
- transfer-only blocks are still not allowed
- included transactions become `settled` immediately after accepted block persistence
- settled transactions no longer count toward `pending_outgoing` or `pending_incoming`
- settled outgoing transfers reduce final balance
- settled incoming transfers increase final balance
- included transactions are removed from the local mempool

Task 8.7 validation rules:

- peer blocks with native transfers validate against chain-before-block state
- synced chains with native transfers are validated block by block in order
- canonical block ordering for native transfers is `from_address`, then `nonce`, then `tx_id`
- peer-provided local transaction status is not authoritative for settlement
- mempools remain local and are not consensus-wide

## Balance Fields

Native account summaries expose these balance snapshot fields:

- `final_balance`
- `native_balance`
- `pending_outgoing`
- `pending_incoming`
- `available_balance`
- `nonce.next_nonce`
- `nonce.policy`

Current balance rules:

- `pending_outgoing` includes accepted outgoing non-final transfers
- `pending_incoming` is display-only
- `available_balance = final_balance - pending_outgoing`
- `native_balance` remains equal to `final_balance` for compatibility
- final balance is chain-derived and includes settled native transfers from accepted blocks
- settled transaction counts and pending transaction counts come from canonical native transaction history

That also means:

- `signed_pending` is not the same as settled
- `mempool` is not the same as settled
- transfer recording must not be described as complete or confirmed
- settlement happens only through accepted meme-mined blocks

## Transaction History UX

Canonical native account history now centers on `GET /accounts/{wallet_address}/transactions`.

User-facing lifecycle wording:

- `signed_pending`: Signed native ZOID transfer recorded. Not settled yet.
- `validated_pending`: Signed native ZOID transfer recorded. Not settled yet.
- `mempool`: In local mempool. Not settled yet.
- `included`: Included in meme-mined block.
- `settled`: Settled on ZoidbergChain.
- `rejected`: rejected
- `failed`: failed
- `expired`: expired

History fields should clearly distinguish:

- direction: incoming or outgoing
- final balance versus available balance
- pending outgoing versus pending incoming
- included block height and hash for settled transfers
- rejection reason for rejected transfers

Important wording:

- native ZOID is not an ERC-20 or Ethereum token balance
- pending outgoing transfers reduce available balance
- transfer-only blocks remain disallowed by design
- replacement policy still is not implemented
- persistence reload revalidates native transactions before nonce or balance reservation is trusted again
- backup/export/import snapshots now preserve native transfer state
- current hardening level is for controlled dev/testnet use, not production deployment

## Compatibility Notes

- legacy development wallet endpoints remain available for compatibility reads
- the product should prefer native account wording when referring to MetaMask-backed identities
