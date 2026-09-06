# Milestone 4 Task 4.9: durable native-transaction burst benchmark

## Environment and fixture

The authoritative run used Windows 11 (10.0.26200), Python 3.13.5, SQLite
3.49.1, and a 24-logical-CPU Intel host. SQLite used `journal_mode=delete`,
`synchronous=FULL` (`2`), and a 30,000 ms bounded busy timeout.

Every input was a valid, independently signed Protocol v1 native transfer
submitted through `Blockchain._admit_signed_transfer_durably`. The primary
fixture used 128 funded senders, strictly sequential sender nonces, and the
fixed valid recipient `0x000000000000000000000000000000000000dead`. Fixture
creation was deliberately outside the admission timer: key generation took
0.173 s and parallel signing took 15.522 s (16 fixture workers).

## Optimization history

Measured profiling first found whole-document deep copies dominating the
durable path. SQLite admission now makes isolated shallow copies of the
native mutable collections while retaining the same `BEGIN IMMEDIATE`, full
validation, outbox insertion, and commit-before-ack boundary. The 1,000-item
single-worker calibration improved from 203.843 s (4.906 tx/s) to 124.098 s
(8.058 tx/s).

Further profiling found repeated normalization of already canonical durable
wallet addresses and repeated normalization of unchanged relational rows.
Canonical-address comparisons now short-circuit only exact lower-case durable
addresses (with a legacy normalization fallback), and unchanged relational
rows retain duplicate/conflict checks without re-canonicalization. The final
1,000-item calibration completed in 39.482 s (25.328 tx/s), with a 10.767 s
restart. Focused reliability checks passed after each change.

## Authoritative 10,000-admission result

| Metric | Result |
| --- | ---: |
| Attempted / acknowledged / rejected / unexpected | 10,000 / 10,000 / 0 / 0 |
| Concurrency | 1 durable writer |
| Measured duration | 15,333.908 s |
| Measured throughput | 0.652 tx/s |
| p50 / p95 / p99 / max latency | 211.162 / 399.193 / 627.226 / 6,496,281.333 ms |
| SQLite busy/lock retries | 0 |
| DB before / after | 376,832 / 72,806,400 bytes |
| Approximate storage growth | 7,242.957 bytes per durable transaction |

The host experienced substantial scheduling pauses during this long run;
those pauses are included in the honest wall-clock duration and maximum
latency. They are not interpreted as SQLite lock retries or admission errors.

## Restart durability

The same 10,000-record SQLite database was closed and reopened. Reopen plus
pending-state reconstruction took 194.415 s. It recovered 10,000 pending
records with zero duplicate durable records, zero incorrect active nonce
reservations, and zero incorrect pending balance reservations.

`acknowledged_missing_after_restart = 0`

## Separate contention profiles

The concurrent profiles are intentionally separate from the primary result.

| Profile | Transactions | Senders | Workers | Throughput | p50 / p95 / p99 / max |
| --- | ---: | ---: | ---: | ---: | --- |
| Low contention | 1,000 | 128 | 4 | 27.167 tx/s | 32.131 / 117.495 / 1,082.978 / 7,482.312 ms |
| Sequential pressure | 1,000 | 4 | 4 | 30.607 tx/s | 32.333 / 95.994 / 2,287.722 / 9,535.436 ms |

Both profiles acknowledged every input with zero rejections, unexpected
errors, lock retries, restart losses, duplicates, nonce errors, or balance
reservation errors. Their restart times were 9.975 s and 10.207 s,
respectively.

## Peer propagation and offline recovery

The peer test admitted 1,000 sender transactions and created 1,000 durable
outbox rows. It attempted and ACKed all 1,000, delivered 1,000 unique durable
receiver records, had zero retries and zero outstanding rows, and converged
in 81.461 s (12.276 tx/s). Thirty-two deliberate duplicate replays were
idempotently recognized; receiver duplicate records remained zero.

The offline test held a 256-item receiver-unavailable backlog, recorded 256
pre-reconnect retry attempts, deliberately lost one ACK after a durable
receiver commit, and converged 9.105 s after reconnect. It left zero
unacknowledged rows; the one duplicate delivery was idempotent.

## Content settlement sample

Ten admitted records were settled through a real certified content block, not
a transaction-only block. The block created 10 canonical claims with zero
duplicate canonical sender/nonce claims.

`duplicate_settlements = 0`

## Remaining limitations and risks

SQLite admission is correctly serialized to protect nonce and balance
reservations. Pending-state scans and JSON-backed transfer-intent persistence
still make latency grow with a very large mempool. The authoritative timing
also includes host scheduling pauses, so it is not a service-level capacity
claim. Future scalability work should add durable indexed pending-state
summaries while preserving the validation, lifecycle, outbox, deduplication,
and reorg guarantees exercised here.
