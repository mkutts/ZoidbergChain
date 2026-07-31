# Native Account Model

As of Friday, July 31, 2026, MetaMask-backed `0x...` addresses are the canonical native ZoidbergChain account identity, and Task 8.6 adds meme-block settlement on top of local mempool handling, sender nonce reservation, available-balance limits, and peer transaction gossip.

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

## Balance Fields

Native account summaries expose these balance snapshot fields:

- `final_balance`
- `native_balance`
- `pending_outgoing`
- `pending_incoming`
- `available_balance`

Current balance rules:

- `pending_outgoing` includes accepted outgoing non-final transfers
- `pending_incoming` is display-only
- `available_balance = final_balance - pending_outgoing`
- `native_balance` remains equal to `final_balance` for compatibility
- final balance is chain-derived and includes settled native transfers from accepted blocks

That also means:

- `signed_pending` is not the same as settled
- `mempool` is not the same as settled
- transfer recording must not be described as complete or confirmed
- settlement happens only through accepted meme-mined blocks

## Next Planned Steps

- Task 8.7 hardens block validation and peer-chain compatibility for native transfers

## Compatibility Notes

- legacy development wallet endpoints remain available for compatibility reads
- the product should prefer native account wording when referring to MetaMask-backed identities
