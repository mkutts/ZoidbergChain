# Milestone 7 Task 7.16 — Isolated atomic certification

Dates: 2026-10-21–22 (America/New_York). Protocol v2 / block v3 remain inactive.
MODEL A, original-byte SHA-256 identity, identity/1 and zstd/1, independent
review quorums, exact reduced fractions, and the 3 MiB complete-record limit
are unchanged. This is an offline unified storage laboratory, not a production
database migration or live-chain certification endpoint.

## Repository verification and deliverables

Expected branch: `Compression-State-Bloat-and-Node-Economics`.
Starting HEAD: `4944acadb117cb18eae0d17a21a71c48ea611b91` (separate Task 7.15).
Initial worktree was clean. Relevant prerequisites: `4e86480` (7.14), `b6c85ff`
(7.13), `3a93bff` (7.11), `4cfd6ff` (7.10C). No applicable `AGENTS.md` was found.
The five requested architecture reports were read; inspection covered existing
SQLite transactions, history/reviewer/reputation reconstruction, replay keys,
block persistence, canonical reorganization and retained finality.

Pre-edit verification: **258 passed in 578.40 s**, covering all Task 7.11,
7.13, 7.14 and 7.15 cases. Logs and JUnit: `temp/task716-baseline-host.log`
and `temp/task716-baseline-host.xml`. An initial sandbox run was stopped; final
executions used the host environment documented by earlier milestones for
worker/server tests. No test,
worker containment rule, assertion or application policy was weakened.

Deliverables are the new `canonical_v3/atomic.py`,
`tests/test_milestone_7_task_7_16_atomic.py`, this report, and the verification
summary in `benchmarks/milestone_7_task_7_16_results.json`. No active source,
historical fixture, dependency, public API, storage factory or activation switch
is modified. No commit, staging, push, merge, reset, deployment or subsequent
task is performed.

## Authoritative state and invariants

| State | Authority and lifetime |
| --- | --- |
| Original media and creator | Adapter-issued immutable prepared reference; the existing byte validator and full v1 admission verifier run at preparation. Persisted submission ownership and exact source certificate are independently checked again inside certification. The canonical candidate retains full reconstructible media. |
| Creator rights and review signatures | Externally supplied signed records from the accepted full v2 journal snapshot. Immutable bytes; independently verified by the existing evidence issuer. No runtime signing or key generation. |
| Acceptance/challenge provenance | The trusted local `FrozenReviewJournal` contract from Task 7.15. Missing acceptance is incomplete. This task does not invent historical daily-policy/challenge data absent from the application. |
| Historical eligibility, established status, penalties | Immutable local SQLite history image, authenticated through Task 7.15 `_History`, the unchanged eligibility and reputation services, signed accepted participation and reproduced offenses/penalties. Current status labels do not grant eligibility. |
| Epoch participation | Verified historical distinct-submission participation plus permanent v2 issuance reservations in this SAME database. Two dimensions in one epoch consume one participation at their earliest reference height. Reservations prevent concurrent quota oversubscription; they do not invent reputation promotion from unsupported v2 history. |
| Source selected/finalized history | Immutable snapshot image; current snapshot is a mutable compare-and-swap pointer. Previously finalized source records and ancestry must remain byte-for-value equal when installing a later snapshot. |
| Parent ledger and reward capacity | Explicit trusted offline ledger checkpoint in the immutable snapshot: parent height/hash/time, integer balances/nonces and reward pool. Parent must match the snapshot head/time. The existing construction bridge checks sequential native transfers and mandatory reward capacity. |
| Issued certificate and replay claims | Immutable issuance operation, exact v2 certificate and original application certificate, unique permanent claims; all provisional candidate persistence effects commit together. Issuance does not settle a reward or authorize minting. |
| Candidate canonical bytes | Immutable canonical R, validated by the existing bridge/parser/decoder with all mandatory evidence and budgets. Candidate-to-operation and candidate-to-validation-snapshot links are immutable. |
| Block and transaction indexes | Derived projections of R. Transaction IDs and original hashes are nonunique across competing candidates. |
| Offline canonical selection | Mutable selected path/tip plus branch-owned selected claims; changed together. The caller supplies the winner. No fork-choice score or live-chain authorization is introduced. |
| Finality | Separate externally signed proof plus externally authenticated validator/equivocator context, using unchanged isolated finality verification. Proofs are immutable and protect selected ancestry. |

Preparing, persisting, selecting and finalizing are four different operations.
A successful certification returns `PersistedCandidate` with
`classification='persisted_provisional'`. It reports persistence, not a promise
that the block is currently selected or finalized. Later status is obtained from
the selected path and retained proof. The approved format requires no future
validator signature inside R; missing separate finality never authorizes a
fabricated proof. Absent admission evidence, parent ledger, or explicit native
selection produces an incomplete outcome without claims or block writes.

## Single-file transaction and snapshot boundary

`AtomicV3Store` requires explicit `TestOnlyConfig(context, True)`, an explicit
path and the existing isolated decoder. Creation requires `initial=TrustedSnapshot`
and exclusive creation of a new file. Reopening requires the exact unified
schema, application ID `0x5A563316`, schema version 1 and full pinned context.
Existing active databases, empty files, unknown schemas and block-only Task 7.11
stores are refused. Existing schemas are checked before changing journal mode.
There is no migration path or default production filename.

The default is `journal_mode='DELETE'`, `synchronous=EXTRA`. Reopening must
request the existing journal mode; the constructor refuses implicit conversion.
Optional `journal_mode='WAL'` requires SQLite 3.51.3+, or a published fixed
3.50.7+ / 3.44.6+ backport in those release families, and uses synchronous FULL.
An affected runtime is refused with local `StorageUnavailable` before touching
either a new path or an existing file. The installed SQLite is **3.49.1**.
No runtime/dependency or active store was upgraded or changed.

`TrustedSnapshot.capture` reads the existing trusted application database through
`SQLiteHistoryReader` in one read transaction. The accepted journal records are
read in that transaction. SQLite's supported backup API copies its consistent
state into memory, then `serialize` produces the retained image. No main/WAL
file-copy snapshot is used. A local digest commits the full context, history
image, complete selected review/rights bytes and ledger checkpoint. This is a
local revision identifier, not a new block commitment or a peer state proof.

The retained image is an immutable BLOB INSIDE the unified database. A temporary
in-memory SQLite connection deserializes it read-only for reuse of the existing
history/reviewer services. That connection is only a derived projection; it
has no independently durable state and performs no durable writes. Source
database changes after capture do not change this authority. A newly accepted
source checkpoint must be explicitly installed with the expected current
snapshot ID. This detached snapshot model is deliberately limited to offline
work and cannot claim to observe future changes in an active application DB.

The exact certification write boundary is:

1. Freeze bounded header/native inputs; verify the adapter reference/context.
2. `BEGIN IMMEDIATE` on the unified connection, before reading current authority.
3. Compare expected snapshot; read and hash-check the immutable snapshot.
4. Reconstruct relevant historical qualifications and penalties; verify stored
   submission ownership, exact original admission, original bytes, both signed
   review dimensions and creator rights through the existing modules.
5. Issue complete v2 evidence; verify an optional Task 7.15 proposal's evidence,
   replay keys, historical revision and selected/finalized heads. Recheck parent
   ledger, reward availability, native ancestry replay, signatures, media and
   complete canonical budgets through the existing construction/storage helpers.
6. Check operation identity and all unique claim ownership. Recompute epoch
   capacity against historical participation AND this database's reservations.
7. Insert certificate, every permanent replay claim and participation reservation.
8. Insert exact R, block/transaction indexes, and operation/snapshot linkage.
9. `COMMIT`; only then return a success acknowledgement.

Every exception before commit, including `BaseException` in the transaction
manager, rolls back all writes. SQLite serialization closes claim and predicate
TOCTOU windows; correctness does not depend on a Python lock. No `ATTACH`,
independently committed persistent database or cross-database application lock
participates. Candidate persistence does not change selection, settlement or
finality. Selection and proof retention each have their own explicit transaction.

## Replay schema and deterministic conflicts

The exact DDL is the module's `SCHEMA` (`BLOCK_SCHEMA + EXTRA_SCHEMA`). Foreign
keys are enabled. Immutable-source triggers reject updates/deletes of snapshots,
certifications, permanent claims, participation and candidate ownership, in
addition to the existing immutable block/finality triggers.

| Table | Constraints and meaning |
| --- | --- |
| `snapshots` | Digest PK; bounded BLOB history/reviews/ledger and full context. Immutable accepted checkpoints. |
| `certification_state` | Singleton PK; current and immutable anchor snapshot FKs. Current pointer changes by write-transaction CAS. |
| `certifications` | Operation PK; snapshot FK; individually UNIQUE original SHA-256, submission ID, certificate digest; exact certificate/application BLOBs. Immutable issuance ownership. |
| `replay_claims` | SHA-256 claim PK and operation FK. One owner for every Task 7.15 `replay_keys` identity. |
| `certification_participation` | PK `(wallet,submission,epoch)`; effective height; operation FK. One participation per dimension pair in that epoch. |
| `candidate_certifications` | Block PK/FK; operation and validation-snapshot FKs. Many blocks may reference one issuance. |
| `selected_claims` | PK `(kind,identity)`; block FK. Derived branch-local original, submission, certificate and native transaction claims. |

Replay key preimages remain Task 7.15's N/G/protocol-2 namespace plus kind and
identity. Kinds are original, submission, certificate, creator nonce/message/
signature, and reviewer submission/dimension/wallet, nonce/message/signature.
The policy digests remain bound to the certificate and pinned store context;
they are deliberately excluded from replay namespaces so policy changes cannot
permit reminting an original. The original key excludes submission and encoding.
Nonce and message claims also cover high-S/signature variants. Separate databases
are NOT a shared replay authority and must not be used as independent writers
for the same network/root. Production policy upgrades need one coordinated
authority, not another empty claim database.

Conflict precedence is operation identity, original, submission, certificate,
shared signed-evidence claim, then reviewer epoch quota. These checks execute
under the writer transaction; SQL uniqueness and FKs enforce their durable
invariants as well. An unexpected constraint/storage error is local failure,
not a consensus-invalid decision.

An operation identifies one immutable certification, not a block proposal.
An identical operation/certificate/application and identical block hash/bytes
is an idempotent retry: no extra row, claim or quota charge. The same operation
may persist additional independently verified candidates, including another
allowed encoding, timestamp or native selection. Reusing its ID for different
certificate/application bytes is a conflict. A second operation cannot claim
the same original, even with valid independent reviews and another submission.
An exact retry must still satisfy the supplied current snapshot precondition;
after authority changes the caller must refresh it. A lost acknowledgement
does not undo commit; retry discovers the retained candidate.

## Reorganization, finality and recovery

Permanent claims belong to issuance, including issued-but-unselected evidence.
They are NEVER released by reorg or unselection. Candidate bytes/ownership and
accepted participation reservations likewise survive. This prevents challenge
or reviewer nonce reuse after an orphaned block.

Branch-local `selected_claims` belong to selected blocks. `select_chain` checks
the expected old tip, verified contiguous ancestry to the retained anchor and
all retained finality targets. It replaces the entire selected path, tip and
derived branch claims in one `BEGIN IMMEDIATE` transaction. Deselecting an
unfinalized branch removes its selected claims; selecting a sibling reconstructs
its claims without recertifying or duplicating permanent issuance. Duplicate
evidence/native IDs within one selected ancestry reject. Competing candidate
indexes themselves stay nonunique. A finalized target or its ancestors cannot
be detached, and proof bytes/trust inputs cannot be replaced.

Snapshot installation preserves all previously finalized SOURCE history and
references. Overlapping source history must also agree with locally retained
v3 finalized targets and their selected ancestors. Old snapshots remain available to reproduce older certifications;
new penalties or promotion changes affect newly installed authority, never
rewrite the historical evidence. A stale snapshot/proposal yields incomplete,
and a fresh attempt must authenticate the changed status/penalty state again.

Recovery uses SQLite WAL recovery followed by `check_integrity`: exact schema,
SQLite integrity/FKs, snapshot hashes, canonical block/media/index validation,
retained frozen selection, application signatures, historical eligibility,
certificate commitments, exact permanent claim sets, participation projections,
candidate ownership, selected claims and finality proofs. Reopening alone is not
an integrity scan. `backup` uses SQLite online backup and independently verifies
the destination with the unified store type. Inherited block-index rebuilding
can repair block projections; it cannot invent lost authority, certificates,
claims, ledger snapshots, original media or deleted finality. Claim corruption
requires a known-good backup or external authenticated recovery inventory.

No live ledger/reward settlement, queue/manual-block processing, consensus
selection or v2 reviewer promotion journal is implemented. Parent state is only
available where an explicit authenticated offline ledger checkpoint exists;
unknown descendant state is incomplete. The storage selection primitive is
not complete live-chain reorganization integration.

## Failure semantics and SQLite limitations

| Outcome | Handling |
| --- | --- |
| Invalid admission/cryptographic evidence | Existing `IntegrationError` invalid-admission/canonical classification; no durable writes. No active consensus verdict emitted. |
| Missing or stale evidence/state | Existing `IncompleteEvidence` / `IncompleteConstruction` with named missing facts; no claims/block. |
| Durable duplicate/conflicting issuance | `CertificationConflict` with stable code; preserve existing owner and all bytes. |
| Busy/locked, unavailable worker, storage I/O/full, unexpected local failure | `IntegrationError(LOCAL_FAILURE)` at certification; existing local storage exceptions for maintenance. No false invalid-media or consensus decision. |
| Successful persistence | `PersistedCandidate`, explicitly provisional; commit precedes acknowledgement. |

The default single-file rollback journal, `synchronous=EXTRA`, foreign keys and
SQLite's writer transaction provide the crash-atomic boundary. SQLite documents
EXTRA's directory synchronization on journal deletion in its
[synchronous reference](https://www.sqlite.org/pragma.html#pragma_synchronous).
`BEGIN IMMEDIATE` obtains writer ownership before authority reads, as described
in the [transaction reference](https://www.sqlite.org/lang_transaction.html).
Optional WAL commits are not atomic across multiple attached database files;
this design uses none. SQLite/filesystem locking,
durable fsync, device behavior and a supported local filesystem are assumptions.
Process-death tests do not simulate physical power loss, broken firmware or
network-filesystem durability. Resource-bound worker failures remain operational.
The 64 MiB history-image / 16 MiB journal / 1 MiB ledger caps are local laboratory
resource limits, not new consensus rules. Full images and repeated verification
under a writer lock are intentionally unsuitable for production-scale throughput.
No attacker-with-full-file-control or arbitrary-database-import guarantee is made.

The current SQLite [WAL-reset advisory](https://www.sqlite.org/wal.html#walreset)
identifies a rare corruption race in versions through 3.51.2 when concurrent
checkpointing and WAL resets align. Passing crash/concurrency tests on 3.49.1
does not disprove that race. It was discovered during this task's documentation
review, so the new store defaults to DELETE/EXTRA and refuses affected WAL
runtimes. Four optional WAL process-death cases require a fixed runtime and
remain explicitly unverified here. The existing Task 7.11 WAL implementation
and its historical tests are unchanged; their passing results cover their tested
scenarios, not this advisory's checkpoint race. Fixing that older implementation
or upgrading the runtime is outside this task. No application-lock workaround
or assumption about a low probability is used to claim safe WAL operation.

Snapshot capture and backups use the supported
[SQLite online backup API](https://www.sqlite.org/backup.html) while the source
read transaction remains open. Memory projections have no second durable commit.

## Verification and remaining prerequisites

Final verification used Windows, CPython **3.13.5**, SQLite **3.49.1** and the
existing project environment. All final executed cases passed:

| Selection | Result | Pytest elapsed |
| --- | --- | ---: |
| Pre-edit Task 7.11 / 7.13 / 7.14 / 7.15 | 258 passed | 578.40 s |
| Final Task 7.16, DELETE/EXTRA plus affected-runtime WAL refusal | **45 passed, 4 skipped** | 621.75 s |
| Post-edit Task 7.11 / 7.13 / 7.14 / 7.15 / 7.10C and codec/sequence tests | **559 passed** | 649.55 s |
| Historical Milestone 6 certification/disputes; Milestone 5 reviewers/certificates/reputation; v1 protocol, certified minting and quorum finality | **227 passed**, one existing JUnit `record_property` warning | 421.29 s |

The 559 cases comprise 53 storage, 68 admission/construction, 60 issuance,
77 authenticated-history, 119 canonical-format and 182 codec/sequence cases.
There are **831 distinct final passes and four skips**, with no final failures
or errors. The skips are exactly the four optional WAL process-termination
stages, gated on the missing SQLite WAL-reset fix. They are not counted as
passing WAL verification. No full-repository, native Linux, hardware power-loss
or independent decoder/interoperability run is claimed.

The earlier superseded WAL-path diagnostic run passed 43 cases, including its
four process-death scenarios, but cannot establish safety against the published
checkpoint race on this runtime. After the journal decision, the ENTIRE final
coordinator suite was rerun. Exploratory/baseline/transition runs overlap final
coverage and are not added again. An exploratory test-harness method-name error
was corrected before the final run.

| Observable persisted-state check | Final evidence |
| --- | --- |
| Identical original, simultaneous connections AND simultaneous processes | One winner; loser `original_claim`; one certificate, one candidate, 62 claims. |
| Exact operation retry | No additional certificate, claim, candidate or participation row; identical R and idempotent result. |
| Same certificate, competing candidates / identity versus Zstd | Two distinct retained R/hash values, one certificate and 62 permanent claims; same exact reconstructed original. |
| Independent valid originals | Two certifications and 14 participation reservations. Conflicting same-H submissions leave the first owner unchanged. |
| Serialized epoch predicate | Four existing certifications plus two independent simultaneous attempts yield one new winner and one `reviewer_epoch_quota`; five certificates / 35 participations remain. |
| Exceptions before claims / after claims / after block before commit | All nine stage/error combinations roll back certificate, claims, participation, R and indexes; retry succeeds. |
| Forced process termination at those three pre-commit stages | Two independent recovery scans each observe zero new certificates/claims/blocks; retry succeeds. |
| Forced process termination after commit / lost acknowledgement | One complete certification persists; exact retry is idempotent. No half-committed claim set. |
| Real SQLite busy and real SQLITE_FULL | Explicit local failure, unchanged durable state, successful retry after clearing the local condition. Injected I/O exceptions and unavailable worker outcomes likewise remain local. |
| Stale snapshots/proposals; changed historical promotion or signed penalties | Stale authority is incomplete; refreshed contradictory/ineligible history rejects before persistence. Old immutable history remains reproducible. |
| Reorg and finality | Selected claims follow the chosen provisional branch; permanent claims survive unselection. Failed selection restores the entire old state. Retained v3 finalized ancestry and overlapping source snapshots cannot conflict. |
| Recovery and backup | Exact R/media/transaction IDs, application/evidence history, claim sets and ownership reproduce after reopen and online backup. FKs and immutable-source triggers reject orphaned/overwritten ownership. |

Detailed long outputs and JUnit are retained in `temp/task716-safe-atomic.*`,
`temp/task716-final-canonical.*` and `temp/task716-historical.*`.
The [machine-readable summary](../benchmarks/milestone_7_task_7_16_results.json)
records exact counts, per-classname case counts, skipped node names/reasons,
source checksums, runtime and persisted-state observations.

Run from the repository root with the existing `.venv`; every basetemp and
database is disposable. The host environment was used for the existing local
server and isolated workers. Nothing installs packages or changes the runtime.

```powershell
New-Item -ItemType Directory -Force temp/task716-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task716-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_16_atomic.py -vv --tb=short --basetemp=temp/task716-safe-atomic --junitxml=temp/task716-safe-atomic.xml *> temp/task716-safe-atomic.log
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_11_storage.py tests/test_milestone_7_task_7_13_admission.py tests/test_milestone_7_task_7_14_issuance.py tests/test_milestone_7_task_7_15_history.py tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py -q --tb=short --basetemp=temp/task716-final-canonical --junitxml=temp/task716-final-canonical.xml *> temp/task716-final-canonical.log
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_6_task_6_4_submitter_attestation.py tests/test_milestone_6_task_6_5_dual_review.py tests/test_milestone_6_task_6_6_admission.py tests/test_milestone_6_task_6_8_post_mint_dispute.py tests/test_milestone_5_task_5_5_earned_reviewer_eligibility.py tests/test_milestone_5_task_5_6_certificate_v3.py tests/test_milestone_5_task_5_7_reviewer_reputation.py tests/submissions/test_originality_certificate.py tests/blockchain/test_certificate_block_validation.py tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/integration/test_task_3_7_concurrent_certified_minting.py tests/blockchain/test_task_3_5_validator_quorum_finality.py -q --tb=short --basetemp=temp/task716-historical --junitxml=temp/task716-historical.xml *> temp/task716-historical.log
```

Deterministic fixtures reuse the published Task 7.13/7.15 scalar identities and
real signed source admissions. New independent originals/submission IDs/nonces
are deterministically signed only in test code. The fixture's symbolic trusted
chain/root is not a mined production chain or an arbitrary-database validation
proof. Child processes receive already signed input records and never sign.

Production activation remains blocked by approved launch N/W/G/policy/statement
context, the accepted fresh-v2 full-selection/challenge journal and freeze policy,
complete v2 participation/offense history, queue/manual-block and live ledger
authorization, consensus-driven snapshot/selection/reorg integration, externally
authenticated validator/finality context, coordinated recovery inventory,
resource/retention limits, independent security/decoder/interoperability review
and target-platform containment validation. Admission signatures still do not
directly sign G; the existing prohibition on N reuse across roots remains.
This task introduces no signing/schema amendment or cross-launch history mapping.

Final branch/HEAD are unchanged. The final worktree contains exactly the four
new unstaged deliverables listed above; tracked-file and staged diffs are empty.
Active v1/v2 source is byte-for-byte unchanged, and the selected historical
regressions pass. UTF-8, Python syntax, JSON parsing, source checksums, final
newlines, whitespace and `git diff --check` were verified.

**Task 7.16 is ready for review and a later authorized commit as an isolated
DELETE/EXTRA implementation.** Optional WAL verification requires a fixed
runtime and rerunning its four cases. Production activation is not ready.
No activation, migration, commit/push/merge or subsequent task was performed.
