# Task 9 Block Production And Consensus Extraction

Date: 2026-09-03

## Scope And Preflight

The initial branch was `Repository-Hygiene-and-Core-Refactor` at
`edf0a48a795b33dabc787b6c2b8c59f913fb4128`. That commit is the separate Task 8
native-ledger, mempool, and reward extraction. The worktree was clean before Task 9
editing, and no prompt/repository mismatch was found.

This change is limited to block production, consensus validation, fork choice,
depth-derived finality, facade delegation, direct characterization tests, and this
documentation. It does not change routes, peer synchronization, storage schemas,
dependencies, frontend code, genesis fixtures, or Protocol v1 rules.

## Ownership Inventory

| Responsibility formerly implemented in `Blockchain` | Task 9 owner |
|---|---|
| Candidate media inspection, canonical payload hashing, full-byte embedding, size checks, legacy transaction selection, native-transaction metadata, creator/voter reward ordering, and `Block` construction | `BlockProductionService` |
| Candidate tip/index/hash checks and transaction validation | `BlockValidationService` |
| Protocol v1 media, network, content hash, and full Model A byte validation | `BlockValidationService` |
| Certificate linkage/context, creator reward metadata, voter reward eligibility/caps/order linkage, and native transaction metadata/order/nonce/balance/replay checks | `BlockValidationService` |
| Previous-hash linkage, per-block hash recomputation, canonical genesis validation, and whole-chain validation | `BlockValidationService` |
| Cumulative originality score and deterministic score, height, then lower-tip-hash fork choice | `ForkChoiceService` |
| Protocol block lookup, canonical confirmations, confirmed/finalized phases, and the operational-depth policy | `FinalityService` |

## Deliberately Retained In `Blockchain`

The facade remains the only authoritative owner of the chain and persisted
collections. It retains candidate acceptance and its existing side-effect order:
validate, update miner bookkeeping, append, settle native transfers, prune legacy
pending transactions, reject skipped native transactions, update duplicate caches,
recompute the reward pool, and save. It also retains chain replacement orchestration,
canonical submission reconciliation, native-transaction reconciliation, and
persistence. These stateful workflows were not moved because doing so would either
duplicate state ownership or hide save/reconciliation coupling.

Operational finality remains a derived status, not BFT or cryptographic
irreversibility. The existing behavior that a valid preferred chain can replace the
selected chain remains unchanged; canonical and finality views are then recalculated.
No new reorganization restriction or consensus rule was introduced.

## Design And Dependency Direction

Each facade call builds a fresh `BlockProductionState`,
`BlockProductionCollaborators`, or `BlockValidationCollaborators` view. Collections
are referenced rather than copied, but the view itself is never cached; JSON/SQLite
reloads and chain replacement therefore cannot leave a service bound to an obsolete
list. Runtime-configured values are also supplied per call, preserving existing test
and deployment overrides.

Consensus services depend only on protocol/domain objects and explicit callbacks to
the already extracted ledger, mempool, reward, content, and originality behavior.
They do not import `Blockchain`, `api`, FastAPI, peer transport, or persistence and
cannot call `save_blockchain`. Peer code continues to consume the unchanged
`Blockchain` public methods; networking and synchronization were not refactored.

## Preserved Behavior

- Canonical serialization, field names/order, hashing inputs, block and transaction
  ordering, reward ordering, certificate semantics, and timestamp placement are
  unchanged.
- Protocol v1 blocks still store the complete accepted media bytes and validate
  `media_hash` and `content_hash` against those bytes.
- Native signatures, nonce/replay rules, balances, zero-fee policy, canonical block
  order, and settlement metadata are unchanged.
- Creator and voter reward source, amount, caps, deterministic eligibility records,
  duplicate protections, and transaction linkage are unchanged.
- Fork choice remains originality score, then height, then lexicographically lower
  latest-block hash. Finality remains confirmations `2`, finality `6`, model
  `operational_depth`, scope `policy_not_bft`.
- The canonical genesis media SHA-256 remains
  `dfba5a7e5e8e5f5da047a2ed58660c9d52665c39f2793da90cba51419f8525c7` and the
  canonical genesis hash remains
  `2b99e87f80e0e855ab98b3269b635be5415273f41d7d4bf1a2aeb8b277b13061`.

## Verification

All verification uses Python 3.13 with a unique writable temporary directory and
JUnit report for each pytest run. Final commands, counts, exit codes, durations, and
any evidence gaps are recorded in the Task 9 handoff rather than copied into this
design document.
