# Peer Networking

As of Saturday, August 1, 2026, ZoidbergChain peer networking supports native transaction gossip in addition to existing submission, vote, certificate, and block transport, and Task 8.10 hardens peer-received transaction and block handling for controlled dev/testnet use.

## Transaction Transport Model

There are two separate authorization layers:

- user transaction signatures authorize native ZOID transfer intent payloads
- peer auth or signed peer message transport authorizes node-to-node delivery

Important rule:

- peer-received transactions do not require local wallet sessions

## Native Transaction Peer Endpoints

Implemented endpoints:

- `POST /peers/transactions/receive`
- `GET /peers/transactions/{tx_id}`
- `GET /peers/mempool/summary`
- `POST /transactions/{tx_id}/broadcast`

## Receive Rules

When a node receives a peer transaction:

- it validates peer transport auth separately from the transaction signature
- it validates canonical transaction shape
- it validates deterministic `tx_id`
- it validates the signed message and recovered signer
- it validates network, nonce, available balance, and fee policy
- it decides local status itself

The local node does not trust peer-provided local-only fields such as:

- `status`
- `admitted_at`
- `created_at`
- `updated_at`
- `rejection_reason`

## Mempool Sync

Lightweight sync helpers:

- `sync_transaction_from_peer(...)`
- `sync_mempool_from_peer(...)`

Current behavior:

- peers may exchange tx IDs through mempool summary
- missing transactions may be fetched individually
- each receiving node still performs its own validation
- mempools may differ between peers
- failed peer mempool admission does not roll back unrelated local settled state
- malformed peer transaction payloads are dropped instead of being trusted into storage

Mempools are non-final local candidate pools. SQLite peers durably retry and
reconcile current pending work, so healthy peers eventually converge on relevant
transaction state after reconnection; this is not an immediate-identical or
consensus-wide mempool guarantee.

## Current Limits

Not implemented:

- replacement policy
- mempool consensus
- transfer-only blocks
- transfer replacement/cancellation policy

## Durable Native Transaction Delivery

SQLite nodes persist one acknowledged outbox row for each active same-network
peer present when a local native transaction enters the mempool. Local admission
does not wait for network delivery. The outbox uses exclusive expiring claims,
keeps retryable failures, and marks a row acknowledged only when the receiver
returns a matching ACK after durable admission or durable idempotent recognition.

The logical transaction-delivery `message_id` is stable across retries. The
existing signed Protocol v1 request headers remain attempt-specific and protect
the complete body with peer authentication and replay controls. Receiver-side
message identity is stored durably alongside the independently admitted native
transaction. JSON storage retains immediate legacy broadcast compatibility but
does not provide these relational durability guarantees.

## Reliable Pending Delivery (Task 4.6)

SQLite runtime starts a single local delivery loop. It claims durable work with
the existing lease, performs HTTP outside the storage transaction, and stores
the next retry time after every temporary failure. The deterministic retry
delays are 2, 4, 8, … seconds, capped at 300 seconds; retries have no automatic
attempt limit and use no jitter. The loop polls every second, requests time out
after three seconds, and an interrupted 30-second lease is safely reclaimed on
the next run.

Temporary connection errors, timeouts, 408/425/429, 5xx, future nonce, and
temporarily insufficient local state retry. Stale nonce and same-nonce conflict
also retry: they reflect a receiver's mutable canonical/mempool view and may be
reversed by fork choice or pending-record removal. A finalized competing
transaction would be irreversible locally, but receive responses do not carry
verifiable finality evidence, so Task 4.6 deliberately preserves delivery
intent until synchronization resolves it. Authentication, wrong-network,
unsupported protocol/version, invalid signature/identity, and immutable
conflict are permanent. Exact canonical `already_settled` recognition is an
idempotent success, so chain sync preceding gossip cannot cause endless delivery.

Every 30 seconds a node reconciles at most 100 current mempool records with
active same-network peers. A newly registered/re-registered peer receives that
bounded pending set; settled history is deliberately left to chain sync. The
mempool summary endpoint is paged and capped at 100 IDs, and bounded pull
reconciliation fetches only missing IDs through the usual validated receive
path. Peer URL changes reuse node-ID keyed unacknowledged work. Removed,
disabled, wrong-network, acknowledged, and permanent-failure destinations are
not automatically revived. Outbox counts and oldest outstanding age are visible
only in existing admin operational diagnostics, never public transaction APIs.

## Security Notes

- peer transport authorization and user transfer signatures are separate checks
- peer-received transactions never require a browser wallet session
- peer-provided local-only fields are ignored and local status is decided by the receiving node
- testnet and production should run with a real peer secret, signed peer messages, and restricted CORS
- current behavior remains appropriate for controlled dev/testnet use rather than production deployment

## Evidence-bound certificate transfer

Milestone 5 certificate version 2 cannot be accepted from a certificate object
alone. Authenticated peers transfer the related submission/vote set, immutable
originality evidence, and canonical media bytes through
`/peers/originality-evidence/receive` before the certificate or certified block.
Evidence can be fetched by digest through
`/peers/originality-evidence/{evidence_digest}`, and chain-sync block responses
include the required evidence transfers.

Receivers verify media SHA-256, rule/runtime identity, evidence digest, canonical
references and candidate ordering, then recompute the complete evidence against
the referenced chain prefix. Missing media, missing evidence, mismatches, and
unsupported rules fail closed. Replaying an identical evidence transfer is an
idempotent success; evidence already bound to an active certificate cannot be
replaced.

## Public Demo Notes

- Stage 1 public deployment is a controlled testnet, not mainnet
- `GET /health`, `GET /node-info`, and `GET /chain/summary` are the safe public status surfaces
- peer counts may be exposed in health metadata, but peer secrets and internal file paths must never be exposed
