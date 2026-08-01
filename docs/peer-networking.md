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

Mempools are local candidate pools and are not consensus-critical yet.

## Current Limits

Not implemented yet:

- replacement policy
- mempool consensus
- transfer-only blocks

## Security Notes

- peer transport authorization and user transfer signatures are separate checks
- peer-received transactions never require a browser wallet session
- peer-provided local-only fields are ignored and local status is decided by the receiving node
- current behavior remains appropriate for controlled dev/testnet use rather than production deployment
