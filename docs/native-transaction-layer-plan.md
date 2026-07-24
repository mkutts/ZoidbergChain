# Native Transaction Layer Plan

Task 8.1 now implements the first hardening step for native ZOID transfer intents by adding the canonical `NativeTransaction` record and deterministic `tx_id`.

- This is a planning document for Task 8.
- It now implements nonce sequencing and replay protection.
- It does not enforce balance sufficiency yet.
- It does not implement a mempool yet.
- It does not settle transfers.
- It does not mutate spendable balances yet.
- It does not include transfers in blocks yet except to define the intended future block shape.

## Task 8.1 Implemented Shape

Canonical native transaction fields:

- `tx_id`
- `transaction_type` with value `native_transfer`
- `network`
- `from_address`
- `to_address`
- `amount`
- `fee`
- `nonce`
- `memo` optional
- `timestamp`
- `signature`
- `signature_scheme`
- `signed_message`
- `signed_message_hash`
- `status`
- `created_at`
- `updated_at`
- `included_block_hash` optional
- `included_block_height` optional
- `settled_at` optional
- `rejection_reason` optional

Task 8.1 persists this record in both storage backends as `native_transactions`.

## Deterministic Transaction ID

Task 8.1 uses:

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

Rules:

- `tx_id` is lowercase SHA-256 hex
- the same signed transaction always produces the same `tx_id`
- changing signer, recipient, amount, nonce, memo, fee, signed message, or signature changes `tx_id`

## Current Status Meaning

`signed_pending` means:

- the signed native transaction record exists
- it has a deterministic `tx_id`
- it is queryable through transaction history and `GET /transactions/{tx_id}`
- it is not settled
- balances do not change yet
- transfer execution remains deferred until later Task 8 steps

Task 8.2 now adds nonce tracking and replay hardening.

## Task 8.2 Nonce Policy

Current policy:

- nonce is per `from_address`
- first native transaction nonce is `1`
- nonce is included in the signed transfer message
- nonce is part of the canonical transaction payload and `tx_id`
- strict sequential nonces are required
- no gaps are allowed
- no replacement policy exists yet

Replay and duplicate handling:

- exact duplicate signed transaction is idempotent by `tx_id`
- same sender plus same nonce plus different `tx_id` is rejected
- lower nonce than the next expected nonce is rejected unless it is the exact known transaction
- higher gap nonce is rejected

Reservation rules:

- `signed_pending`, `validated_pending`, and `mempool` reserve nonce
- `included` and `settled` permanently consume nonce
- current nonce state is derived from persisted transaction records
- restart does not reset nonce state or allow replay

Read endpoint:

- `GET /accounts/{wallet_address}/nonce`
- returns `next_nonce`, `used_nonces`, `reserved_nonces`, and policy

Task 8.3 now adds balance sufficiency enforcement and available-balance calculation.

## Task 8.3 Balance Model

Current balance types:

- `final_balance`: chain-derived native balance only
- `pending_outgoing`: sum of accepted non-final outgoing transactions that reserve funds
- `pending_incoming`: sum of accepted non-final incoming transaction amounts
- `available_balance = final_balance - pending_outgoing`

Current fund-reservation statuses:

- reserves funds: `signed_pending`, `validated_pending`, `mempool`
- does not reserve funds: `rejected`, `failed`, `expired`
- `included` and `settled` are expected to move into final-balance accounting once Task 8.6 settlement exists

Current balance sufficiency rule:

- submit-time acceptance requires `amount + fee <= available_balance`
- insufficient transactions are rejected before record acceptance
- insufficient transactions do not reserve funds
- insufficient transactions do not consume nonce through persisted acceptance
- final balance is not mutated yet because settlement is still deferred

Current fee policy:

- the `fee` field exists for forward compatibility
- nonzero fees are not enabled yet
- fee still counts in the sufficiency formula conceptually, but current submit handling rejects nonzero fee values

Read surfaces now expose:

- `final_balance`
- `pending_outgoing`
- `pending_incoming`
- `available_balance`
- backward-compatible `native_balance` equal to `final_balance`

Task 8.4 adds mempool storage and validation.

Task 8.6 adds block inclusion and settlement.

## Current Starting Point

Task 7.8 already provides a signed transfer-intent flow:

- a verified MetaMask session can request `POST /auth/wallet/transfer-challenge`
- the wallet signs the exact backend-built transfer message with `personal_sign`
- `POST /transfers/submit` stores a signed non-final transfer intent record
- the stored record uses status `signed_pending`
- balances are not reduced
- no mempool admission happens yet
- no peer propagation happens yet
- no block inclusion happens yet

This means the project already has:

- native `0x` wallet identity
- canonical transfer message structure
- deterministic signing message
- transfer-intent persistence
- transfer history read endpoints

It does not yet have:

- transaction id finalization
- balance sufficiency enforcement
- mempool acceptance rules
- peer transaction gossip
- transfer inclusion in meme-mined blocks
- settled balance updates from transfers

## Core Transaction Types

### Signed Transfer Intent

- A user-authenticated and MetaMask-signed request to move native ZOID later.
- Created through the current Task 7.8 endpoints.
- Local to the receiving node for now.
- Non-final and non-settling.

### Pending Transaction

- A normalized transaction record that has passed basic signature and payload checks.
- Not yet fully admitted to the shared mempool.
- May still fail nonce or balance checks depending on validation stage.

### Mempool Transaction

- A validated pending transaction accepted into the node's active transaction pool.
- Eligible for peer propagation and future block inclusion.
- Still non-final until included in a valid block.

### Included Transaction

- A mempool transaction placed into a valid meme-mined block.
- Considered part of the canonical chain only if the block is valid and accepted.

### Settled Transaction

- An included transaction on the accepted chain that now affects final balances.
- This is the point where outgoing and incoming native balances change.

### Failed / Rejected Transaction

- A transaction that cannot proceed because of invalid signature, invalid nonce, insufficient available balance, expiration, conflicting nonce, or block-validation failure.
- May be kept for audit, but it is not part of settled balance state.

## Transaction Lifecycle

Recommended lifecycle:

`draft / unsigned`  
`-> signed_pending`  
`-> validated_pending`  
`-> mempool`  
`-> included`  
`-> settled`

Or:

`-> rejected`  
`-> expired`  
`-> failed`

### `draft / unsigned`

- Meaning: user-entered transfer data before signature.
- Who can create it: frontend or local client only.
- Affects balances: no.
- Propagated to peers: no.
- Can be included in a block: no.
- Final: no.

### `signed_pending`

- Meaning: the transfer message was signed and accepted by the local backend as a transfer intent.
- Who can create it: verified local wallet user through session plus signature.
- Affects balances: no final balance change.
- Propagated to peers: no, not yet.
- Can be included in a block: no.
- Final: no.

### `validated_pending`

- Meaning: the signed record has been upgraded into a canonical transaction candidate and has passed transaction-level validation rules except actual mempool admission timing.
- Who can create it: local node transaction-processing logic.
- Affects balances: no final balance change.
- Propagated to peers: not necessarily; depends on admission flow.
- Can be included in a block: not yet.
- Final: no.

### `mempool`

- Meaning: the node accepted the transaction into its active mempool.
- Who can create it: local node after full transaction validation, or peer ingestion after revalidation.
- Affects balances: no final balance change.
- Propagated to peers: yes.
- Can be included in a block: yes.
- Final: no.

### `included`

- Meaning: the transaction is in a valid candidate or accepted block.
- Who can create it: miner/node assembling a meme-mined block.
- Affects balances: yes for chain-derived final balance once the block is accepted.
- Propagated to peers: as part of block propagation.
- Can be included in a block: already included.
- Final: not fully final until the block is accepted on the active chain.

### `settled`

- Meaning: the included transaction is on the accepted canonical chain and counts toward final balance.
- Who can create it: chain-state interpretation, not direct user action.
- Affects balances: yes.
- Propagated to peers: represented through the chain itself.
- Can be included in a block: already included.
- Final: yes within current chain rules.

### `rejected`

- Meaning: validation failed before mempool inclusion.
- Who can create it: local node or receiving peer.
- Affects balances: no.
- Propagated to peers: no.
- Can be included in a block: no.
- Final: yes for that attempted transaction record unless retried with a new valid signed transaction.

### `expired`

- Meaning: the signed transaction or its policy window is no longer acceptable for admission.
- Who can create it: local node maintenance or startup revalidation.
- Affects balances: no.
- Propagated to peers: no.
- Can be included in a block: no.
- Final: yes.

### `failed`

- Meaning: the transaction was previously accepted for processing but later failed deeper validation, block assembly, or revalidation.
- Who can create it: local node processing.
- Affects balances: no final balance effect if not settled.
- Propagated to peers: optional audit only.
- Can be included in a block: no.
- Final: yes for that record state.

## Nonce Model

Recommended initial Task 8 nonce strategy:

- every wallet has a transaction nonce
- the nonce is signed as part of the canonical transfer payload
- strict sequential nonce per sender wallet
- no gaps
- no replacement policy yet
- duplicate nonce is rejected unless it is the exact same known transaction

### Expected Nonce Source

The expected next nonce should be derived in this order:

1. included and settled transactions already on the accepted chain
2. locally accepted mempool transactions for that same sender

This means:

- settled chain state determines the baseline nonce
- mempool may reserve future sequential nonces
- a sender cannot jump ahead and leave nonce gaps

### Duplicate Nonce Handling

- If the same sender submits the exact same transaction again with the same canonical payload and signature, treat it as idempotent by `tx_id`.
- If the sender submits a different transaction with the same nonce, reject it.

### Gap Nonce Handling

- If the next expected nonce is `5`, nonce `6` is rejected until nonce `5` is either settled or admitted in the pending sequence, depending on the exact Task 8 implementation.

### Replacement Policy

- No replacement policy yet.
- No fee bumping yet.
- No "replace-by-fee" behavior.

This keeps the first transaction layer simple and deterministic.

## Balance Sufficiency Model

Task 8 should separate final balances from pending/mempool views.

### Final Balance

Recommended definition:

`final_balance = settled chain-derived balance`

Sources:

- genesis allocation if applicable
- meme-mining rewards received
- settled incoming transfers
- settled outgoing transfers
- settled fees later if fees are enabled

Signed pending transfer intents must not change `final_balance`.

### Pending Outgoing

Recommended definition:

`pending_outgoing = sum of mempool transactions from this wallet not yet settled`

This is useful for wallet UX and double-spend prevention.

### Pending Incoming

Recommended definition:

`pending_incoming = sum of mempool transactions to this wallet not yet settled`

This is informational only until inclusion.

### Available Balance

Recommended definition:

`available_balance = final_balance - pending_outgoing`

Recommended behavior:

- `final_balance` remains chain-derived and settled only
- `pending_outgoing` reduces spendable view later
- `pending_incoming` is shown separately and does not count as settled spendable balance yet

## Fee Model

Recommended initial Task 8 fee policy:

- keep the `fee` field in the transaction shape
- require `fee == 0`
- reject nonzero fees until fee policy is intentionally designed

Why this is recommended:

- keeps early transaction settlement simpler
- avoids premature miner-incentive design work
- avoids confusion with meme reward accounting
- preserves forward compatibility because the signed message shape already includes `fee`

## Transaction ID Plan

Recommended initial transaction id:

`tx_id = SHA-256(canonical transfer payload + signature)`

Rules:

- the same signed transfer must always produce the same `tx_id`
- modifying `amount`, `to_address`, `nonce`, `memo`, `fee`, or `signature` changes `tx_id`
- `tx_id` is used for deduplication
- `tx_id` is used for mempool tracking
- `tx_id` is used for explorer and block references

Recommended implementation note for Task 8:

- hash the canonical normalized payload fields in stable order
- append or include the signature in the canonical transaction record before hashing
- avoid any non-deterministic fields such as local database ids in `tx_id` generation

## Mempool Validation Rules

Before a transfer enters the mempool, Task 8 should require:

- valid transaction signature
- recovered signer equals `from_address`
- network matches current network
- `from_address` and `to_address` are valid normalized native wallet addresses
- `from_address != to_address`
- amount is positive and decimal-safe
- fee policy is satisfied, initially `fee == 0`
- nonce equals the next expected or otherwise acceptable pending nonce under the strict sequential policy
- sufficient `available_balance`
- not a duplicate `tx_id`
- not a conflicting transaction using the same sender nonce
- message hash matches the canonical signed payload
- any expiration policy is satisfied if one is added

Recommended split:

- local user session auth remains only for the initial local submission path
- transaction signature becomes the network-validating proof

## Block Inclusion Rules

Recommended Task 8 block inclusion model:

- Meme Proof of Originality remains the reason a block is mined.
- A meme block may include zero or more validated native transfer transactions.
- The meme reward is still credited to the signed submission creator wallet.
- Transfer inclusion must not alter originality scoring.
- Transfer validation is part of full block validation.
- Any invalid included transfer causes block rejection.

### Intended Future Block Shape

A future block should continue to include:

- reward metadata
- `submission_id`
- `certificate_id`
- `content_hash`
- `originality_score`

And should additionally include:

- `transactions`: zero or more validated native transfer transactions
- eventually `tx_id` references or full canonical transaction records
- optional `transaction_root` or similar aggregate hash later

### Balance Application Rule

Only included and accepted transactions affect final balances.

Signed intents, validated pending records, and mempool records do not directly reduce final balance.

## Ordering Rules

Recommended initial deterministic ordering for Task 8:

- primary: sender nonce
- secondary: accepted-at timestamp
- tertiary: `tx_id`

Reasoning:

- preserves strict sender sequencing
- keeps ordering deterministic across nodes
- avoids introducing fee-priority policy too early

No complex fee market ordering is recommended yet.

## Peer Propagation Plan

Recommended future peer flow:

1. local node validates a signed transaction and admits it to the mempool
2. local node broadcasts the canonical transaction to active peers
3. receiving peer verifies the signature and canonical payload first
4. receiving peer applies local nonce, balance, and mempool admission rules
5. receiving peer accepts or rejects
6. duplicate `tx_id` is idempotent

Important separation:

- local user session auth is only for local frontend submission
- transaction signature is what the network validates
- peer-received transactions must not require a local verified wallet session token

Recommended initial policy:

- invalid signatures rejected immediately
- wrong network rejected
- conflicting nonce rejected
- duplicate identical `tx_id` accepted idempotently

## Storage Model

Task 8 should distinguish between:

- signed transfer intents
- validated pending transactions
- mempool transactions
- included transactions
- optional rejected/failed audit records

### Recommended Persistence Rules

- included transactions are durable because they are chain-derived
- mempool transactions may persist across restart in development and testnet
- persisted mempool transactions should be revalidated on startup
- rejected and failed records are optional audit metadata, not chain state

### Recommended Storage Shape

Compatible with the current JSON and SQLite snapshot model:

- `transfer_intents`: signed local non-final intent records from Task 7.8
- `mempool_transactions`: canonical validated transaction records awaiting inclusion
- `rejected_transactions`: optional audit-only failure records if the project wants traceability

Recommended startup behavior:

- reload persisted mempool records
- revalidate each one against current chain state and nonce rules
- drop or mark invalid entries rather than trusting them blindly

## Future Balance Calculation

Recommended future chain-derived balance formula:

`native_balance(wallet) = genesis allocation + meme rewards received + settled incoming transfers - settled outgoing transfers - settled fees`

Important rule:

- `signed_pending` transfer intents are not part of final native balance
- mempool transactions are not part of final native balance
- only settled included transfers count in final chain balance

## API Plan For Task 8

Recommended future endpoints:

- `POST /transactions/submit`
- `GET /transactions/{tx_id}`
- `GET /wallets/{wallet_address}/transactions`
- `GET /mempool`
- `POST /mempool/revalidate`

Optional:

- `POST /blocks/{block_hash}/transactions` is probably unnecessary if transfer inclusion happens during normal meme block assembly

Recommended endpoint roles:

- `POST /transactions/submit`
  - local user path
  - requires verified session plus signed canonical transaction submission
  - may evolve from or replace the current transfer-intent endpoint
- `GET /transactions/{tx_id}`
  - public-safe read
- `GET /wallets/{wallet_address}/transactions`
  - public-safe history read
- `GET /mempool`
  - node or explorer diagnostics
- `POST /mempool/revalidate`
  - maintenance or development operation

Peer receive endpoints, if added, should validate transaction signatures and canonical records without requiring local user session auth.

## Frontend Plan For Task 8

Recommended future UI evolution:

- transfer form submits a real canonical transaction rather than just a signed intent
- wallet balance view shows:
  - final balance
  - pending outgoing
  - available balance
  - pending incoming
- transfer history shows:
  - signed pending
  - validated pending
  - mempool
  - included
  - settled
  - failed or rejected
- block explorer shows included native transfer transactions inside meme-mined blocks

Important messaging:

- native transfers are not ERC-20 transfers
- wrapped ZOID remains a later bridge or liquidity topic
- normal MetaMask still does not directly display native ZOID ledger state

## What Is Deferred To Task 8

Task 7.9 defines the plan only.

Deferred to later Task 8 steps:

- balance sufficiency enforcement
- mempool admission and persistence logic
- peer transaction gossip
- block inclusion
- block validation for included transfers
- explorer and wallet views for settled transfer history
