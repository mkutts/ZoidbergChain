# Milestone 3 Release Readiness Report

## Scope and result

This report covers Milestone 3, Task 3.8 only: lifecycle timing instrumentation, the final lifecycle benchmark, and acceptance/readiness review. No commit or push was performed.

The lifecycle benchmark completed 100/100 records. After correcting the delayed-finality harness and batching prompt validator quorum processing, the primary acceptance metric, vote-pass → finalized p95, was **37.654222300 s**. The `<30 s` target is still **not met**, now because of the expected linear commit queue rather than delayed finality.

## Repository state

- Branch: `Consensus-Integrity-Ordered-Minting-and-Finality`
- Starting HEAD: `ff4ab31` (`test: add concurrent ordered minting and finality benchmark`)
- Tasks 3.1–3.7: separate commits `20b7329`, `7c960e2`, `4f69f41`, `436e51d`, `65ea1ab`, `01bae92`, and `ff4ab31`.
- Clean-worktree preflight: PASS; no changes were present before Task 3.8.

## Files changed in Task 3.8

- `services/lifecycle_timing.py`: thread-safe, in-memory lifecycle recorder using monotonic nanoseconds for durations and a non-consensus wall-clock diagnostic field.
- `services/__init__.py`: exports the recorder.
- `blockchain.py`: marks vote passed, certificate created, ready for mint, proposal prepared, accepted, and finalized at the real lifecycle boundaries. It also accepts a received group of finality attestations against one validated chain snapshot and persists the resulting evidence once; every signature, validator, canonical-block, quorum, and finalized-height check remains unchanged. An optional recorder can be shared by benchmark participants; it is not serialized.
- `tests/blockchain/test_task_3_8_lifecycle_timing.py`: recorder contract test.
- `tests/integration/test_task_3_7_concurrent_certified_minting.py`: shares the recorder across the existing 100-approval / 4-commit-worker path, delivers accepted submissions promptly to process-isolated validator replicas, coalesces up to eight received blocks per durable quorum checkpoint, and records percentile properties.

Instrumentation is observational only. It does not enter block payloads, signatures, certificates, hashes, ordering, finality votes, or durable blockchain state. Marks are idempotent so replay and retry do not inflate a stage.

## Milestone 3 architecture

- Deterministic mint ordering sorts certified submissions by `(content_hash, vote_hash, certificate_id)`.
- The authoritative certified commit is `Blockchain.commit_certified_submission`.
- SQLite uses `BEGIN IMMEDIATE`; the JSON backend uses a lock plus compare-and-swap and atomic replacement.
- A stale canonical head raises `StaleCanonicalHeadError`; the coordinator reloads durable state, reselects the first ordered item, and retries with bounded backoff.
- Certified commit identity is the immutable `certificate_id`.
- Storage and block validation enforce unique heights, canonical previous-hash linkage, certificate identity, transaction IDs/nonces, reward IDs, and finalized-chain preservation.
- Finality uses a configured known validator set, signed Protocol v1 attestation messages, persisted attestations/evidence, and the quorum formula `ceil(2N/3)`, implemented as `(2N + 2) // 3`. A received group shares one complete local chain validation and one durable checkpoint; it does not change any per-attestation validation or finalization evidence.
- A block is accepted when durably committed; it is finalized only after persisted validator quorum evidence.
- Fork choice rejects a candidate that changes a finalized height/hash.
- The retry coordinator preserves the canonical queue head across contention and never advances by selecting a later-ranked submission.

### Deterministic ordering

The exact Task 3.2 tuple is `(content_hash, vote_hash, certificate_id)`. These are canonical lowercase SHA-256-derived identifiers from the validated certificate, so honest nodes with the same certified submissions derive the same order independently of insertion or worker timing.

### Atomicity

`Blockchain.commit_certified_submission` is the authoritative entry point. SQLite enters `BEGIN IMMEDIATE`; the JSON backend takes its lock, checks the expected head, and atomically replaces the document. Failures roll back chain append, native settlement, pending-mempool removal, reward settlement, image/text caches, submission mint transition, and queue removal. The canonical head, balances, nonces, transactions, rewards, submissions, queue, and chain are covered by the boundary.

### Idempotency

`certificate_id` is the commit identity. Replaying a request resolves the already committed block before stale-head validation and performs no second transition. Duplicate transaction IDs, sender/nonces, reward IDs, and certificate/block identities are rejected or treated as already settled according to the established Task 3.4 rules; a changed durable submission/certificate produces a conflict.

### Finality

Validator identity is the normalized Ethereum-style validator address. The configured validator set is known and deduplicated. Quorum is `ceil(2N/3)`. Attestations use the Protocol v1 finality domain and signed block-height/hash/network message, are validated and persisted, and finalization evidence records the validator set, quorum, and attestations. Accepted and finalized are separate states. Persisted evidence plus fork-choice checks prevent a finalized-chain reorg.

## Task 3.7 benchmark confirmation

The committed Task 3.7 benchmark report records:

- 100 approval workers; 4 commit workers.
- Exactly 100 blocks at heights 1–100.
- Total workload: 35.871601 s.
- 100-block commit duration: 30.604977 s.
- Throughput: 3.267442 blocks/s.
- Stale-head retries: 0; SQLite busy retries: 0; maximum retries: 0.
- Finality completion: 0.473514 s.
- Healthy validators finalized the same height-100 hash.

## Task 3.8 lifecycle benchmark

The same real concurrency path was run with 100 approvals and 4 commit workers. Each accepted submission was immediately delivered to a process-isolated validator replica. Replicas use a bounded batch of eight received canonical blocks, submit two independently signed attestations per block, validate all attestations and the current chain, and persist per-block quorum evidence in one checkpoint. Percentiles use the nearest-rank method: sort the `n` durations and select rank `ceil(p*n)`, one-indexed. Values are seconds and retain nine decimal places.

| Interval | Count | Min | p50 | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|
| Vote pass → certificate | 100 | 0.079566200 | 0.130763700 | 0.163387900 | 0.167625200 | 0.172240000 |
| Certificate → accepted | 100 | 2.121003100 | 19.992647300 | 35.041135100 | 36.255356000 | 36.465560500 |
| Accepted → finalized | 100 | 0.294533600 | 1.177167000 | 4.638800300 | 5.257353700 | 5.865913800 |
| Vote pass → finalized | 100 | 4.223202600 | 21.692029600 | **37.654222300** | 38.219080200 | 38.221377100 |

Additional measured splits:

| Interval | p95 | Max |
|---|---:|---:|
| Certificate → ready | 1.471152500 | 1.548405400 |
| Ready → proposal/preparation | 34.286502200 | 35.633574200 |
| Proposal/preparation → accepted | 0.037712000 | 0.195293500 |

The lifecycle run produced 100 sequential blocks and zero stale-head, SQLite-busy, or max-retry events. Total duration was 40.978989 s; commit duration was 33.880567 s, or 2.951544 blocks/s. Every submission had its own persisted finalized evidence.

## Bottleneck analysis

The original 193.042374700-second accepted → finalized p95 was a harness artifact. The benchmark committed the entire batch, performed peer synchronization only afterward, then synchronously submitted two attestations to the source and two to the peer for each height 1–100. Its measured sequential finality loop was 211.482355 s, which directly put block 95 behind the batch drain and 94 prior finality operations. There was no polling, timeout, or retry contribution.

After prompt process-isolated delivery and bounded quorum batches, accepted → finalized p95 is 4.638800300 s. Certification is not the remaining bottleneck: vote pass → certificate p95 is 0.163387900 s. Contention/retries are not the bottleneck: all three retry counters remain zero. The remaining delay is the intentional single-head queue: ready → proposal p95 is 34.286502200 s and certificate → accepted p95 is 35.041135100 s, while proposal → accepted itself is only 0.037712000 s p95. The workload's 2.951544 blocks/s means late members of a 100-item deterministic linear queue necessarily wait tens of seconds. No multiple-canonical-block optimization or correctness relaxation was made.

## Test evidence

- Focused instrumentation, atomic commit, idempotency, finality, and public finality status: `34 passed in 10.23s`.
- Lifecycle/concurrency benchmark after the latency fix: `1 passed in 41.65s` using a repository-local pytest base directory.
- Full backend suite: `1012 passed in 140.32s` using `--basetemp=.pytest-task-3-8-full`; no setup errors.
- Frontend tests/build: not rerun; no frontend files changed. Preflight baseline remains 130 passing tests and a passing production build.
- `git diff --check`: PASS.

## Remaining risks

- Controlled validator set; no permissionless validator admission or BFT slashing.
- SQLite whole-document/write-lock scalability under larger bursts.
- Linear-chain queue latency under burst load.
- JSON backend suitability for production workloads.
- Limited process-kill durability evidence beyond the existing fault-injection and replay tests.
- Operational observability is intentionally limited to opt-in debug/test instrumentation.

## Acceptance table

| Criterion | Result | Evidence |
|---|---|---|
| 100 simultaneous approvals produce exactly 100 valid sequential blocks | PASS | Task 3.7 benchmark; lifecycle run; `_assert_canonical_workload`; heights 1–100. |
| No duplicate heights | PASS | Task 3.7/lifecycle workload assertions. |
| No duplicate mints | PASS | Unique submission and certificate assertions plus idempotency tests. |
| No partial settlements | PASS | Atomic commit rollback tests, including injected fault stages. |
| Healthy validators converge on one finalized chain | PASS | Task 3.7 two-node sync/finality convergence and same height-100 hash. |
| Replaying a commit request is safe | PASS | Task 3.4 replay tests and Task 3.7 replay checks. |
| p95 vote-pass → finality <30 s | FAIL | Task 3.8 lifecycle p95 = 37.654222300 s; prompt finality p95 is 4.638800300 s, but deterministic linear commit queueing remains above target. |

Milestone 3 is therefore **not fully accepted**: correctness criteria pass, but the latency criterion fails under the representative 100-submission per-block-finality measurement.
