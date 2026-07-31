# Native Account Model

As of July 30, 2026, MetaMask-backed `0x...` addresses are the canonical native ZoidbergChain account identity, and Task 8.2 enforces sender nonce reservation for accepted signed native transactions.

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

Compatibility read endpoints:

- `GET /wallets/{wallet_address}/transfers`
- `GET /wallets/{wallet_address}/transactions`

These endpoints:

- require an Ethereum-style `0x...` address for native account reads
- normalize addresses consistently
- expose safe read-only fields
- do not require the account to appear in the development wallet registry

## Task 8.1 Transaction Recording

Task 8.1 records each successful signed native transfer submission in two related forms:

- `transfer_id`: local transfer-intent identifier
- `tx_id`: deterministic canonical transaction identifier

Current meaning of `signed_pending`:

- the signed transaction record exists
- the transaction can be queried
- it is not settled
- it reserves the sender nonce
- it does not change balances yet

Task 8.1 account rules:

- balances are chain-derived only
- transfer records do not mutate balances yet
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

## Task 8.1 Balance Reminder

Native account summaries still expose the balance snapshot fields:

- `final_balance`
- `native_balance`
- `pending_outgoing`
- `pending_incoming`
- `available_balance`

For Task 8.1, recorded transfer records do not change balances yet.

That means:

- `signed_pending` is not the same as settled
- transfer recording must not be described as complete or confirmed
- balance mutation is deferred to later transaction-processing work

## Next Planned Steps

- Task 8.3 adds balance sufficiency enforcement

## Compatibility Notes

- legacy development wallet endpoints remain available for compatibility reads
- the product should prefer native account wording when referring to MetaMask-backed identities
