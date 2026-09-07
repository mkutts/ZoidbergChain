# Milestone 4 release-readiness report

Date: 2026-09-06  
Scope: Task 4.10 final verification only; no protocol redesign, commit, or push.

## Final conclusion

**Milestone 4 complete: every acceptance criterion passed.**

This conclusion is for Public Testnet v1 only with SQLite and authenticated peer-delivery configuration. It is not a mainnet claim and does not make the mempool consensus-wide.

## Repository and scope

| Item | Verified value |
| --- | --- |
| Branch | Native-Transactions-Durable-Mempool-and-Reorg-Recovery |
| HEAD | 65d6bf6e7007214b9ad70f43c3bb3d00e669b9ee (task 4.9 done) |
| Worktree before Task 4.10 edits | clean |
| Task 4.9 commit | 65d6bf6 task 4.9 done, separate from Task 4.10 documentation work |
| Milestone commits | 923e134 (4.1), dbc494f (4.2), 46cfba6 (4.3), fd141bf (4.4), 0351834 (4.5), 06ba737 (4.6), 7feac08 (4.7), 7d2f6e5 (4.8), 65d6bf6 (4.9) |

Tasks 4.1–4.9 supplied the baseline audit, relational records, durable-before-ack admission, deterministic validation, outbox/receiver deduplication, retry/reconciliation, atomic reorg recovery, reliability coverage, and burst evidence.

## Transaction lifecycle and durability boundary

Local signed admission, explicit admission, and peer receive call the blockchain durable-admission operations. Each enters storage.atomic_update_blockchain_document; SQLite uses one BEGIN IMMEDIATE transaction for the native record, paired transfer intent, lifecycle history, canonical projections, and (for local mempool admission) outbox rows. Memory is published only after the commit. An accepted local or peer receive response is therefore never returned before its record is durable.

| State | Legal next states | Reservation/finality |
| --- | --- | --- |
| signed_pending | validated_pending, mempool, settled, rejected, failed, expired | active; reserves nonce and available balance |
| validated_pending | mempool, settled, rejected, failed, expired | active; reservation remains |
| mempool | validated_pending, settled, rejected, failed, expired | active, locally block-eligible |
| included | settled, validated_pending, mempool, rejected, finalized | active historical/API-compatible inclusion state |
| settled | validated_pending, mempool, rejected, finalized | active canonical settlement; non-finalized settlement can reorg back to pending |
| finalized | none | active, canonical finality evidence exists |
| rejected, failed, expired | settled only | inactive; release local reservation; canonical inclusion can override earlier local terminal outcome |

The active partial-unique-index states are signed_pending, validated_pending, mempool, included, settled, and finalized. Block selection uses only validated_pending and mempool; block ordering is sender, numeric nonce, then tx_id. Mempool display ordering is operational only. Public/API transaction status derives from transaction state plus canonical block/finality evidence.

Transaction lifecycle is separate from peer delivery. One mempool transaction can have independent per-destination delivery rows.

## SQLite invariants actually enforced

This table is based on the current SQLite DDL and triggers in storage.py and a
fresh instantiated SQLite schema readout (including its live tables, partial
active-sender/nonce index, outbox uniqueness indexes, receiver primary key, and
both state-guard triggers). JSON does not provide these relational guarantees.

| Invariant | SQLite enforced | Application enforced | Both | Notes |
| --- | --- | --- | --- | --- |
| Native tx_id uniqueness | yes | yes | yes | native_transaction_records.tx_id primary key; code rejects immutable-payload conflict |
| Immutable payload for existing ID | no trigger | yes | no | upsert compares immutable_payload; identity validation binds it to tx_id |
| Lifecycle values | yes | yes | yes | CHECK on lifecycle_state |
| Lifecycle transitions | yes | yes | yes | lifecycle guard trigger and ledger transition map |
| Lifecycle history | yes | yes | yes | primary key of tx_id/transition sequence and foreign key; application appends entries |
| Active sender/nonce uniqueness | yes | yes | yes | partial unique index over active states |
| Pending balance sufficiency | no | yes | no | requires canonical balances and all active reservations |
| Canonical transaction claim | yes | yes | yes | canonical tx_id primary key |
| Canonical sender/nonce claim | yes | yes | yes | unique sender/nonce constraint |
| Canonical reward claim | yes | yes | yes | reward_id primary key |
| Outbox identity | yes | yes | yes | outbox primary key; unique message ID/destination pair |
| Outbox values/attempt count | yes | yes | yes | state and non-negative-count CHECKs |
| Outbox transitions | yes | yes | yes | state guard trigger; claim-token handling uses guarded SQL/code |
| Lease exclusivity/recovery | partly | yes | yes | one BEGIN IMMEDIATE, claim predicates/token/expiry, and claimable index |
| Receiver message deduplication | yes | yes | yes | receiver message ID primary key; code verifies type, sender, tx_id, and payload-hash binding |
| Canonical/reward rebuild on reorg | atomic boundary | yes | yes | atomic replacement deletes/repopulates claim projections |

Outbox indexes cover claimability and tx_id; receiver messages have a tx_id index. The receiver primary key alone does not prove payload binding, and the immutable representation does not by itself forbid update: those exact properties remain application-enforced.

## Application and protocol invariants

| Rule | Enforcement and why not pure SQLite |
| --- | --- |
| Canonical serialization and tx_id binding | Protocol builders reconstruct canonical intent and domain hash; SQL is not the protocol serializer |
| Signed-message hash and MetaMask recovery | Validation recomputes hash, exact message, and Ethereum signer recovery; cryptography is outside SQL |
| Sender/signature, network, protocol/version | Validation compares recovered signer, configured network ID, and supported versions |
| Nonce sequencing and balance reservations | Validation derives chain next nonce and available balance from canonical state and active rows |
| Deterministic block validation/order | Ledger/block validation replays balances, nonces, canonical IDs, and block-local duplicate sets |
| Peer authentication | HTTP signature/replay-window checks use transport data and secrets separately from user signatures |
| Retry/permanent classification | Delivery worker interprets HTTP/protocol outcomes; mutable nonce/balance outcomes deliberately stay retryable |
| Anti-entropy validation | Bounded summaries/fetches enter the ordinary authenticated durable receive path |
| Reorg orphan validation | Candidate records are checked against reconstructed winning-chain state |
| Finality boundary | Fork choice and atomic adoption compare persisted finalized height/hash against candidate chain |

## Peer delivery lifecycle

| State | Behavior |
| --- | --- |
| queued | claim to in_flight, or permanent failure for inactive/removed/wrong-network destination |
| in_flight | matching ACK -> acknowledged; retryable result -> retry_wait; immutable/protocol failure -> permanent_failure |
| retry_wait | due work can be claimed again; permanent failure is allowed |
| acknowledged | terminal and not claimable; exact duplicate ACK is harmless |
| permanent_failure | terminal and not automatically revived |

Default retry is min(300, 2 * 2^(attempt_count - 1)) seconds: 2, 4, 8, …, 300, without attempt limit or jitter. The worker polls each second, uses a three-second request timeout and a 30-second lease. Stale in-flight leases become retry_wait; network I/O occurs after the claim transaction.

Receiver ACKs bind logical message ID and tx_id; exact existing receiver message or canonical settlement is idempotent success. Lost-ACK retry cannot duplicate admission or settlement. Authentication, wrong network, unsupported version, invalid signature/identity, and message conflict are permanent. Timeouts, 408/425/429, 5xx, future/stale nonce, active nonce conflict, and temporary balance insufficiency retry because they depend on mutable local canonical/mempool state.

Every 30 seconds, at most 100 current mempool records reconcile with active peers. New/re-registered peers reuse node-ID keyed rows and may expedite pending retry. Bounded pull reconciliation uses the normal validated receive route; settled history remains chain-sync work.

## Reorg and finality audit

Blockchain.adopt_canonical_chain performs fork choice and finality preservation before replacement, then repeats both checks against the durable document inside atomic update. CanonicalReorgService.branch_delta finds the common ancestor by hash and previous-hash lineage, never height alone.

The one SQLite transaction includes the winning document, native rows and lifecycle history, active reservations, canonical native/reward claims, finality metadata, and requeued outbox rows. The reorg rebuild validates/replays the winning chain to reconstruct balances and next nonces, marks winning transactions settled, rebuilds transfer intents and canonical claims, rebuilds creator/voter reward claims, reconciles submissions/mint queue, and removes detached noncanonical attestations.

Detached candidates are ordered by sender, numeric nonce, existing-pending preference, and mempool key. Each is revalidated against winning state: valid orphaned transactions return to mempool; invalid ones become rejected with a reorg-prefixed reason. Requeued transactions receive idempotent outbox work in the same transaction. Repeated adoption returns already_canonical. Memory publishes only after commit, so post-commit/pre-publish failure recovers from durable state after restart.

Every persisted finality record must exist at the same height/hash on the candidate. The preflight and durable recheck reject any candidate that replaces finalized history. Accepted but non-finalized blocks, their native transactions/rewards, and their attestations remain intentionally reorg-sensitive. No audited adoption path bypasses finality protection.

## Benchmark audit

The Task 4.9 benchmark report, benchmark script, and focused test were inspected. The script independently signs Protocol v1 transactions and sends them through the durable-admission path; it does not bypass signatures, network, nonce, balance, SQLite, or durable-before-ack admission. It accounts for every attempted outcome, reopens SQLite to check actual IDs/reservations/balances, exercises real outbox/receiver behavior, and settles the sample in a certified content block. No retained raw benchmark artifact is in the repository, so the Task 4.9 report is the authoritative recorded run and the script/test verify its calculation path.

| Evidence | Verified recorded result |
| --- | --- |
| Admission | 10,000 attempted; 10,000 acknowledged; 0 rejected; 0 unexpected |
| Restart | 10,000 recovered; no duplicate records, nonce reservation errors, or balance reservation errors; **acknowledged_missing_after_restart = 0** |
| DB math | 376,832 -> 72,806,400 bytes; (72,806,400 - 376,832) / 10,000 = 7,242.9568 bytes/transaction |
| Healthy peer workload | 1,000 delivered/ACKed; 0 retries; 0 outstanding; 0 receiver duplicates; 12.276 tx/s; 81.461 s |
| Offline recovery | 256 backlog; 256 pre-reconnect retries; one idempotent lost-ACK duplicate; 9.105 s; 0 rows remaining |
| Settlement sample | 10 canonical claims; **duplicate_settlements = 0** |
| Safe calibration | 4.906 -> 25.328 tx/s with validation, SQL transaction, outbox insertion, and commit-before-ack retained |

The 10,000-run wall clock of 15,333.908 s (0.652 tx/s) includes documented host scheduling pauses. It is not a clean capacity claim; neither is calibration a production capacity claim.

## Operations, deployment, and remaining limits

Restart of 10,000 pending rows took **194.415 seconds**. Code/benchmark evidence attributes this to pending-state reconstruction/validation, scans, transfer-intent persistence, and large record materialization—not data loss or SQLite lock retries. It is a **significant Public Testnet limitation**, not a correctness release blocker.

| Pending records | Approximate pending-record storage, excluding Model A media |
| ---: | ---: |
| 10,000 | 72.43 MB |
| 100,000 | 724.30 MB |
| 1,000,000 | 7.24 GB |

The measured 12.276 tx/s healthy peer rate limits burst convergence at larger testnet scale and suggests future indexed/batched scheduling work. Full Model A immutable media growth is separate and can be materially larger.

Public Testnet v1 requirements:

1. STORAGE_BACKEND=sqlite is mandatory for native-record, receiver-deduplication, and peer-outbox guarantees.
2. Use a unique data directory/database per node; stop before JSON-to-SQLite migration, back up first, integrity-check after migration, and verify restart before retiring the backup.
3. Set a secret-manager-provided PEER_SHARED_SECRET; enable signed messages and REQUIRE_PEER_AUTH=true outside development.
4. Retain tested delivery settings unless deliberately revalidated: poll 1 s, initial retry 2 s, maximum retry 300 s, timeout 3 s, lease 30 s, reconciliation 30 s, batch 100.
5. Monitor outbox backlog, retry_wait, permanent failures, oldest outstanding delivery age, storage integrity, and restart duration using admin operational diagnostics.

Mempools are locally admitted, non-final candidate pools. Healthy SQLite peers eventually reconcile relevant current pending state, but arrival timing, retry/backoff, bounded anti-entropy, partitions, later-added peers, and state-dependent temporary rejection can produce temporary differences. The system does not guarantee immediate identical mempools and does not treat mempool contents as consensus. JSON retains compatibility/local-development behavior only and cannot support the Public Testnet Milestone 4 durability claim.

| Risk category | Assessment |
| --- | --- |
| Correctness | No failing Milestone 4 criterion found |
| Scale/performance | Significant restart time, roughly 7.24 KB/pending record, serialized durable admission, 12.276 tx/s measured peer convergence |
| Operational | SQLite/auth/configuration/monitoring are mandatory; permanent outbox failures need operator action; host scheduling distorts long wall-clock benchmarks |
| Future decentralization | Known validator set, no mempool consensus, no replacement policy, bounded eventual anti-entropy, and no mainnet claim |

## Acceptance matrix

| # | Acceptance criterion | Result | Current evidence |
| ---: | --- | --- | --- |
| 1 | No acknowledged transaction silently disappears | PASS | atomic durable admission; restart test; zero missing benchmark |
| 2 | Duplicate delivery cannot duplicate settlement | PASS | receiver binding/claims; 4.6 lost-ACK and 4.8 restart tests |
| 3 | Restart preserves accepted pending transactions | PASS | relational records; 4.8 restart test and 10,000 recovery |
| 4 | Reorg restores canonical state | PASS | reorg rebuild; 4.7 atomic test |
| 5 | Reorg restores balances | PASS | winning-chain replay; 4.7 test |
| 6 | Reorg restores sender nonces | PASS | next-nonce rebuild; 4.7 test |
| 7 | Reorg restores canonical claims | PASS | atomic claims rebuild; 4.7 test |
| 8 | Reorg restores creator rewards | PASS | winning-chain reward rebuild; 4.7 test |
| 9 | Reorg restores voter rewards | PASS | reward-claim replacement; 4.7 test |
| 10 | Valid orphan returns pending | PASS | deterministic revalidation/requeue; 4.7 test |
| 11 | Invalid orphan is not blindly requeued | PASS | reorg rejection; 4.7 test |
| 12 | Healthy nodes converge after reconnection | PASS | durable retry/reconciliation; 4.6/4.8 and peer benchmark |
| 13 | Durable peer outbox survives restart | PASS | SQLite outbox/lease design; 4.5/4.6 tests |
| 14 | Lost ACK recovery is idempotent | PASS | stable logical ID/receiver dedup; 4.6/4.8 tests |
| 15 | Admission durable before acknowledgement | PASS | atomic boundary; 4.3 storage-failure test |
| 16 | Active sender/nonce uniqueness | PASS | SQLite partial index; 4.2/4.8 concurrency tests |
| 17 | Pending oversubscription prevented | PASS | reservation validation; API/4.8 tests |
| 18 | Wrong network/signature/version deterministic reject | PASS | validation service; 4.4, peer, Protocol tests |
| 19 | Finalized history not silently reorged | PASS | preflight + durable finality checks; 4.7/Task 3.5 tests |
| 20 | Transaction ordering deterministic | PASS | sender/nonce/ID key; 4.8 and block validation tests |

## Test and security evidence

- Focused Task 4.2–4.9 reliability and benchmark-selection suite: **105 passed in 16.18 s**.
- Native API/account, ledger/mempool, peer auth/message, block validation/production, finality, and Protocol/golden-vector suite: **169 passed in 10.57 s**.
- Full backend suite using workspace-local writable temporary storage: **1,072 passed in 132.03 s**.
- Backend compileall completed successfully for all root Python modules plus the API, service, test, and script packages.
- git diff --check completed successfully.

The security regression audit retained MetaMask signature recovery, canonical tx_id/signed-message binding, network/version validation, nonce/replay and balance checks, authenticated peer transport, access-control separation, Model A content-integrity/storage, and validator finality.
