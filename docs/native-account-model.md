# Native Account Model

Task 7.12 clarifies that MetaMask-backed `0x...` addresses are the normal native ZoidbergChain account format going forward.

## Core Model

- A verified MetaMask signer becomes a native ZoidbergChain account.
- The native account identifier is the normalized lowercase `0x...` address.
- Native ZOID balances live in ZoidbergChain state, not in normal MetaMask asset display.
- Old generated server wallets remain development-only test tools and are not the primary user account model.

## What A Native Account Can Own

A native account may accumulate:

- signed meme submissions
- signed originality votes
- native ZOID meme-mining rewards
- signed transfer intents
- canonical native transaction records with deterministic `tx_id`

No pre-registration step is required in the old dev-wallet list. A `0x` address becomes a native account as soon as chain activity references it.

## Read APIs

Task 7.12 introduces native account read endpoints:

- `GET /accounts/{wallet_address}`
- `GET /accounts/{wallet_address}/submissions`
- `GET /accounts/{wallet_address}/votes`
- `GET /accounts/{wallet_address}/rewards`
- `GET /accounts/{wallet_address}/transfers`
- `GET /accounts/{wallet_address}/transactions`

These endpoints:

- require an Ethereum-style `0x...` address
- normalize the address consistently
- expose safe read-only fields
- do not require the account to exist in the development wallet registry

Compatibility endpoints also remain available:

- `GET /wallets/{wallet_address}/transfers`
- `GET /wallets/{wallet_address}/transactions`

## Task 8.1 Native Transaction Layer

Task 8.1 records each successful signed native transfer submission in two related forms:

- `transfer_id`: local transfer-intent record identifier
- `tx_id`: deterministic canonical native transaction identifier

Current status meaning:

- `signed_pending` means the transaction was recorded and can be queried
- `signed_pending` does not mean settled, confirmed, complete, or balance-changing
- `signed_pending` now reserves the sender nonce immediately
- nonce is per native `from_address`
- first native transfer nonce is `1`
- strict sequential nonce policy is active
- exact duplicate signed transaction is idempotent by `tx_id`
- conflicting same-sender same-nonce transaction is rejected

Nonce read endpoint:

- `GET /accounts/{wallet_address}/nonce`

Important current rules:

- balances are not reduced yet
- native accounts remain MetaMask/Ethereum-style `0x` ZoidbergChain accounts
- old dev wallets are still not the native account registry
- Task 8.2 adds nonce tracking and replay protection
- Task 8.3 adds balance sufficiency enforcement

## Legacy / Compatibility Notes

- `GET /get_wallets`, `POST /generate_wallet`, and `GET /dev/wallets` remain development-only server-wallet tooling.
- Older `/wallets/{wallet_address}/...` read endpoints may continue to exist as compatibility endpoints during the transition.
- The product UI should prefer native account wording over generic wallet wording when referring to MetaMask-backed ZoidbergChain identities.

## Task 8 Dependency

Task 8 transaction hardening should build on this account model rather than reintroducing a separate end-user wallet identity format.
