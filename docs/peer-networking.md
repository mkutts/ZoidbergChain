# Peer Networking

As of Friday, July 31, 2026, ZoidbergChain peer networking supports native transaction gossip in addition to existing submission, vote, certificate, and block transport.

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

Mempools are local candidate pools and are not consensus-critical yet.

## Current Limits

Not implemented yet:

- block inclusion of native transfers
- settlement of native transfers
- replacement policy
- mempool consensus

## Next Step

- Task 8.6 adds native transfer inclusion in meme-mined blocks and settlement behavior
