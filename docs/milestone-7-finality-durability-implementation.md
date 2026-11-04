# Milestone 7 Task 7.17E — Local finality durability implementation

Date: 2026-10-24 (America/New_York).

**Local reliability repair only. No distributed BFT or agreement guarantee.**
The existing quorum, validator configuration, finality signing preimages, block
hashes and fork-choice rules are retained. Protocol 2 / block 3 remain inactive.
Task 7.17 reviewer-history integration remains blocked by the independent
authority/agreement gates in [Task 7.17D](milestone-7-finality-safety-and-remediation-decision.md).

## 1. Repository prerequisites and scope

- Expected/actual branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting HEAD: `f025e6097cceca6b9286bf2cefaff35825fff7a7`, separately committing
  Task 7.17D, `Milestone 7 Task 7.17D: specify finality safety and remediation`.
- Starting index/worktree clean. Task 7.17C remains separately committed at
  `3b8bbce70fa0c35827b48d499760bca2c3bfd56a` with its audit and diagnostics.
- Read [7.17C](milestone-7-finality-and-history-dependency-audit.md) and 7.17D;
  current implementation and tests were inspected as authority. No applicable
  repository/ancestor `AGENTS.md`; no delegation.
- Tests use disposable workspace databases and ordinary disposable test signing
  accounts. No operational validator key is provisioned. No live database is
  modified, migrated, reset or converted to another journal mode.
- No consensus replacement, rounds, signer/anti-equivocation protocol, membership
  redesign, quorum change, history integration, deployment, commit, push or merge.

## 2. Original defects, baseline and preserved witnesses

The original **unchanged** Task 7.17C suite ran before any production edit:
**17 passed in 1.83 s**, `temp/task717e-baseline.log` / `.xml`. Passing assertions
reproduced known defects; this was not a safety pass.

| Defect | Original path and deterministic witness |
| --- | --- |
| Lost concurrent vote | Two `submit_validator_finality_attestations` calls copy the same empty facade list, independently count one vote and later overwrite each other's whole-document state. The barrier diagnostic leaves one persisted vote and no QC. |
| Stale finality erasure | A current facade saves a QC; an older facade's `save_blockchain` replacement erases votes and QC. Reproduced on JSON and SQLite despite the existing backend lock/transaction. |
| Failed save leaves memory ahead | Submission assigns `self.finality_attestations`, `self.finalized_blocks` and report projection before calling `save_blockchain`. Injected failure leaves a QC in memory with no durable save. |
| Duplicate retry skips recovery | An exact repeat enters the old duplicate path, never saves and reports the non-durable in-memory finalization. |

The historical defect assertions are **preserved**, not inverted, deleted, skipped
or marked expected-failure. Their facade harness now explicitly uses the two exact
pre-repair method bodies in [`tests/finality_717c_baseline.py`](../tests/finality_717c_baseline.py).
Those bodies come from starting HEAD `f025e60`; their concatenated normalized-LF
SHA-256 is `af0ad219385481992b793329f1be39bc6b86d34de8628a141c3c25fc3ba24a80`.
The historical suite explicitly bypasses the new storage guard within its own
monkeypatch fixture, recreating the old write contract. This unsafe test-only
snapshot is never imported by production or by the new durability suite.

Thus four existing defect cases (two stale-save backends, failed-save/retry and
concurrent loss) continue to demonstrate the old behavior as historical evidence.
Their expected outcomes on **current** production are separately asserted in
[`tests/test_milestone_7_task_7_17e_finality_durability.py`](../tests/test_milestone_7_task_7_17e_finality_durability.py).
The surviving signature, quorum, split-vote, authority and proof-context
diagnostics still exercise the existing service semantics. No historical green
count is presented as proof that current defects remain or that BFT is achieved.

## 3. Files and call paths

| File | Change |
| --- | --- |
| [`blockchain.py`](../blockchain.py) | Transaction-bound finality submission, commit-before-publish, uncertain-outcome reread, serialized writers/cache publication, monotonic refresh checks, unavailable recovery state and detached proof copies. |
| [`services/finality_service.py`](../services/finality_service.py) | Authenticate first, then deduplicate by exact canonical signed message rather than exact signature spelling. No signing/threshold/membership rule change. |
| [`storage.py`](../storage.py) | Common monotonic QC/vote guard at JSON and SQLite document-write boundaries; explicit guarded reorg exception for detached unfinalized votes; SQLite DELETE/EXTRA/timeout/connection ownership; no schema addition. |
| [`tests/test_milestone_7_task_7_17e_finality_durability.py`](../tests/test_milestone_7_task_7_17e_finality_durability.py) | Current-code concurrency, real signatures, fault injection, disk-full, corruption, retries, restart and actual process-termination tests. |
| [`tests/finality_717c_baseline.py`](../tests/finality_717c_baseline.py) | Version-pinned unsafe historical methods, exclusively for preserving original witnesses. |
| [`tests/test_milestone_7_task_7_17c_finality_audit.py`](../tests/test_milestone_7_task_7_17c_finality_audit.py) | Explicit historical harness/version label; original test assertions retained. |
| [`tests/integration/test_two_node_consensus_verification.py`](../tests/integration/test_two_node_consensus_verification.py) | One finality test now gives the second node an independent temporary SQLite store. Its finality/order assertions are unchanged. |
| [`tests/test_milestone_6_task_6_8_post_mint_dispute.py`](../tests/test_milestone_6_task_6_8_post_mint_dispute.py) | The unfinalized-media negative test now constructs media without finalizing it, instead of attempting to erase a committed QC. Its rejection assertion is unchanged; an added assertion verifies no media QC exists. |
| This report | Implementation boundaries, evidence, compatibility and remaining gates. |

Current flow:

```text
submit_validator_finality_attestation -> batch submission
  -> process-local storage-identity writer lock
  -> storage.atomic_update_blockchain_document
      -> SQLite BEGIN IMMEDIATE / JSON OS lock
      -> authoritative chain, retained votes and QCs read under that boundary
      -> existing chain/target/signature/membership verification
      -> duplicate detection, vote collection and quorum/QC creation on private document
      -> all-writer finality preservation guard
      -> document and existing relational projections written
      -> commit / JSON atomic replacement
  -> publish committed chain/finality caches
  -> rebuild report lookup, emit lifecycle notifications, reconcile reviewer caches
  -> return result
```

Reviewer reconciliation retains its existing separate persistence semantics. It
is not included in a purported transaction spanning independent files. Failure
after commit can surface to the caller while finality remains committed; an exact
retry obtains the durable result and can repeat the existing idempotent follow-up.

## 4. Exact atomic boundary and durable uniqueness

SQLite submission performs chain validation, target hash verification, canonical
attestation authentication, membership checks, duplicate lookup, vote addition,
quorum aggregation and first-QC creation on the fresh document supplied by
`atomic_update_blockchain_document` **after `BEGIN IMMEDIATE`**. Votes/finality no
longer originate from a pre-transaction facade snapshot. No separate expected
head CAS is needed for this command: it validates the actual locked chain and
existing finality, including finality changes with no head change.

The existing backend transaction also writes canonical claims, native transaction
lifecycle/projections, review/evidence projections and storage sections. All
affected SQLite writes use that same connection and transaction. The connection
context must finish committing before the backend returns. A callback result
alone is not a successful commit. The injected precommit test raises after SQL
writes but before the connection context commits; it verifies rollback of both
vote and QC sections. Actual process termination is tested at that same window.

Logical vote identity is the exact authenticated canonical **message**, which
already binds validator, network/domain/protocol, height and target hash. Incoming
signatures still undergo the existing full validation before duplicate detection.
An identical signed message with another valid ECDSA signature representation
returns duplicate; it cannot occupy another vote slot. The first retained signed
record is preserved. Quorum counting still validates retained signatures and
counts unique eligible validator addresses under the existing policy.

`_preserve_finality` applies a union by message at every repository document-write
boundary. Equal message with contradictory authenticated fields rejects rather
than overwriting. A different target's vote is not a duplicate; normal submission
rejects a noncanonical target under existing rules. Existing live equivocation
logic is unchanged; this task adds no off-branch evidence acceptance protocol.

**No migration or new SQL table/index is required.** Existing `storage_sections`
primary keys store the complete finality sections. The reserved SQLite writer
lock serializes the read, procedural uniqueness/union predicates and write for
all guarded application writers, including separate processes. JSON uses its
OS-held commit lock for the equivalent logical operation. This is enforceable
application-level uniqueness within the existing architecture, not a claim of a
new relational vote index. Manual SQL, deletion/replacement of the DB file and
external rollback are outside those application write APIs.

## 5. Monotonic storage rules and reorganization

The guard runs in SQLite's `_save_sections_to_connection` while a write transaction
is active. It rereads the actual persisted chain/finality sections on that same
connection, so even `_save_sections`, direct saves, stale callbacks, ordinary
atomic commands and imports using these APIs cannot bypass it. A bare call
without an explicit transaction is refused. JSON's public document save now
acquires the OS lock; atomic commands call its internal locked writer without
reacquiring that lock. The merged document is returned to its caller.

Rules:

1. Carry forward all durable finalized targets, even when omitted by an older
   snapshot. A stale compatible save cannot erase votes or QCs.
2. Same-height/different finalized hash rejects with `FinalityStateConflictError`.
   Same-target alternate proof bytes do not replace the first durable QC.
3. Every retained/new finalized target must exist at the exact height/hash in
   the resulting selected chain. The complete prefix through the highest anchor
   must be contiguous and hash-linked; the previously finalized prefix's index,
   hash and parent identities cannot change. A higher height is no exemption.
4. Additional older compatible QCs are allowed without lowering the highest
   finalized head. Gapped finality remains supported; no parent-QC rule is added.
5. Retain the durable union of canonical finality votes. Ordinary saves cannot
   detach an unfinalized voted target either; they must use the guarded canonical
   reorg path instead of silently truncating or replacing that history.
6. `adopt_canonical_chain` explicitly passes `allow_vote_reorg=True`, after its
   existing full candidate/fork-choice/durable finality checks. This permits the
   established removal of votes belonging to a detached **unfinalized** branch.
   It never permits detaching QCs or finalized ancestry. The exception is an
   internal storage command contract, not remote authorization or a new fork rule.

Storage guards preserve identities/ancestry and immutable first proofs. They do
not invent a historical validator-authority registry or reinterpret proof
validity: signature/authority checking remains at the existing service/facade
boundaries. All current received-vote promotion paths validate before committing.
Administrative raw storage is not a consensus verification API.

The race tests force both transaction orders. If finality commits first, the
reorg is refused; if the permitted unfinalized reorg commits first, an attestation
for the now-detached target is refused. Both inspect actual finality/vote rows
after the race. No score or arrival-order preference resolves conflicting QCs.

## 6. Cache, failure, retry and recovery discipline

No finality vote/QC/report lookup is assigned by the submission callback. It
works on a private durable document. Publication follows successful commit.
Storage-identity reentrant writer locks serialize finality submissions, generic
saves and reloads in one process; SQLite/JSON locks supply cross-process write
serialization. A separate per-facade reentrant cache lock protects publication,
full restore and public head/state/proof reads. Cache locks are not held across
the finality database transaction.

Before a restore mutates the selected chain, its finality transition is checked:
duplicate heights, invalid new proof bytes, target mismatch and loss/conflict of
known committed QCs reject. A late same-chain refresh retains already confirmed
canonical votes. Thus an older postcommit callback cannot overwrite newer
committed finality in that facade. Public proof retrieval returns a deep copy,
so editing a returned signature list cannot mutate the authoritative cache.

| Window/failure | Result and retry contract |
| --- | --- |
| Before commit, including actual SQL write failure | Transaction rolls back. No new finality was published; reread restores committed state. Retrying the new vote can accept it. |
| Actual process death after SQL writes before commit | Parent observes old votes/no QC; SQLite recovery rolls back; retry after restart accepts exactly once. |
| Commit completed before publication/acknowledgement | Durable new votes/QC survive. Submission rereads on a new connection after an exception, refreshes caches and preserves the original error; exact retry is duplicate. |
| Actual process death after commit before response | Parent observes the complete new votes/QC; fresh facade reconstructs them; retry is duplicate. |
| Busy/locked, disk full or I/O failure | Original local operational error surfaces. No vote is declared invalid because of storage failure; no partial QC is published. An ambiguous outcome is reread rather than assumed rolled back. |
| Outcome reread also fails | Mark finality unavailable. Head/state/proof and finalized-reference/dispute checks refuse use until successful recovery; old cache is not asserted as current authority. A subsequent successful durable submission/reload can recover it. |
| Reload validation fails | Finality remains unavailable. Existing proof-error wrapping for invalid persisted protocol material is preserved. OSError, SQLite errors and runtime/storage failures propagate as operational failures rather than being relabeled invalid media/evidence. |
| Missing storage after known finalized state | Refuse empty recovery; do not reset known committed finality. A fresh uninitialized store may still create the existing pinned genesis. |
| One of the finality section pair is missing | Refuse automatic empty initialization. A truly pre-finality legacy database with both absent retains the existing initialization compatibility path. |

The loader temporarily withholds external finality reads while rebuilding state;
its own recovery thread can run the existing reconciliation queries. It clears
unavailability only on successful return. Corrupted proof recovery is tested
with a real complete facade on JSON and SQLite, followed by explicit test repair
and repeated successful reload.

Submission's uncertain-outcome recovery also revalidates the reread durable
chain before publishing it. A failed chain validation cannot be followed by an
unvalidated restore that incorrectly clears the unavailable state. A stale
generic save refreshes the derived report-finality lookup after publishing the
committed finality fields; a full-facade shared-store test verifies that view too.

Idle facades in other processes may have an older committed view until their next
operation/reload; no network invalidation service is claimed. They cannot use
that view to erase durable finality through the guarded APIs. No software can
independently detect a completely substituted older valid database on a fresh
node without an external trusted high-water mark/history. Backup rollback/key
custody and signer-state recovery remain separate 7.17D gates; this repair does
not create a signer or a cross-machine monotonic counter.

## 7. SQLite and filesystem operating contract

Observed Python runtime: **CPython 3.13.5; SQLite 3.49.1**.

| Setting / ownership | Implemented behavior |
| --- | --- |
| Journal | Explicitly require existing `DELETE`; refuse another journal mode without automatic conversion. No WAL opt-in or runtime upgrade. |
| Synchronization | Set and read back `synchronous=EXTRA` (3) on each active-storage connection. This is a connection setting, not a DB migration. |
| Busy timeout | Existing 30,000 ms retained; the focused busy test temporarily uses 1 ms on its disposable connection to assert operational failure. |
| Ownership | One connection per `_connect` context, normal SQLite thread ownership, explicit close in `finally`; no connection shared across threads/processes. |
| Write transaction | Existing `BEGIN IMMEDIATE` before authoritative read; connection context commits on normal exit or rolls back on exception. No nested BEGIN; nested-BEGIN refusal tested. |
| Filesystem | Supported local locking/VFS and truthful OS/device flush behavior are assumed. Process-kill tests do not prove physical power-loss durability on arbitrary storage hardware or network filesystems. |

The SQLite [transaction reference](https://www.sqlite.org/lang_transaction.html)
supports the single-writer and busy-handling contract. The
[synchronous reference](https://www.sqlite.org/pragma.html#pragma_synchronous)
explains DELETE/EXTRA's directory synchronization. These database mechanisms
support a correctly scoped read-modify-write; they do not repair a stale
precomputed replacement by themselves.

An existing active-storage database in WAL or another journal mode now fails
closed instead of being silently used/converted. Choosing a supported alternative
requires a separate operating-profile review. The isolated
`canonical_v3.atomic.wal_is_fixed` guard and its affected-runtime refusal remain
unchanged. Optional isolated WAL termination cases are not counted as passes on
3.49.1. No atomicity across independent database files is claimed. JSON retains
its existing file flush/replacement mechanics; no new hardware power-loss or
cross-file guarantee is asserted.

## 8. Verification results and reproduction

Test evidence is under ignored `temp/task717e-*`; every output/basetemp is
disposable and distinct. Tests assert persisted vote/QC records after faults,
not only returned flags or in-memory lists.

| Category | Result and evidence |
| --- | --- |
| Original pre-edit diagnostics | **17 passed**, 1.83 s; `temp/task717e-baseline.xml` |
| Final focused durability/recovery and active finality | **78 passed**, 58.98 s; `temp/task717e-final.xml`. Includes 35 current durability cases, 17 historical witnesses, 6 unchanged legacy storage cases and 20 active finality/status/lifecycle cases. |
| Derived report-finality cache after stale save | **1 passed**, 1.09 s; `temp/task717e-cache.xml`. Additional current durability case, bringing that suite's distinct passing cases to **36**. |
| Finality/status/lifecycle/services/reorg/two-node/storage/outbox | **106 passed**, 67.29 s; `temp/task717e-final-regression.xml` |
| Peer chain/block/certificate/vote APIs and certificate block validation | **84 passed**, 66.41 s; `temp/task717e-peer.xml`, host access to avoid the Windows loopback-socket sandbox stall documented in 7.17C/D |
| Canonical/signing/history/atomic certification | **143 passed, 4 skipped**, 945.12 s; `temp/task717e-canonical.xml`. Skips are the existing affected-runtime WAL process-termination cases. |
| Active v2 admission/activation and reporting | **51 passed** in the completed combined run; `temp/task717e-admission-complete.xml`, restricted to the three corresponding files. The superseded dispute fixture failure in that run is described below. |
| Post-mint disputes, after fixture correction | **14 passed**, 74.94 s; `temp/task717e-dispute.xml`. The entire dispute file passed, including the unchanged unfinalized-media rejection assertion. |

The repaired assertions cover concurrent distinct votes and identical retries on
both backends and shared/separate facades; real signature variants; separate
process writers; stale facade, low-level save and callback overwrite; equal-height
and higher-ancestry conflicts; invalid batches and conflicting votes; busy/full/I/O
faults; lost acknowledgement and failed reread; stale cache refresh; real-facade
corruption/repeated reload on both backends; missing section refusal; gapped
finality, permitted reorg and both reorg/finality race orders; and actual process
termination before/after COMMIT. Separate process tests use genuine signatures
prepared by the parent, not a mocked signature verifier. The small structural
facade stubs unrelated full-media validation explicitly; complete historical
blockchain/API tests retain their ordinary validators.

The two additional COMMIT tests exercise SQLite's actual transaction exit: one
authorizer refuses COMMIT with `SQLITE_AUTH`, and one established reader prevents
the writer obtaining its commit lock, yielding `SQLITE_BUSY`. Both verify the
old durable vote/QC sections and cache remain intact, then retry successfully.
These complement the SQL-write/precommit exception and real page-limit
`SQLITE_FULL` tests; they do not simulate storage failure by classifying a vote
as invalid.

Earlier focused selections also passed (55 cases in 36.51 s and the two COMMIT
cases in 1.15 s); their cases are included in the final focused coverage and are
not counted again. The 20 active finality/status/lifecycle cases overlap the
106-case regression group. Distinct totals below deduplicate exact test IDs.

Final distinct results: **457 passed, 4 skipped**, with **no unresolved failing
case**. Categories are **36 new current durability tests**, **17 preserved
historical diagnostic cases**, and **404 other regression passes**. Of those
other passes, two tests needed the explicit fixture corrections described here;
their original negative/finality assertions were preserved. The remaining
historical cases passed unchanged. The four skips are exactly Task 7.16's optional
WAL process-termination cases on the affected SQLite runtime, not successful WAL
verification. Source/settings tests retain the WAL refusal.

One existing two-node finality test unintentionally used the same database for
both nodes. The first regression run exposed its assumption that each node's
first vote could not combine with the other's durable vote. The fixture now
uses an independent temporary database, preserving every finality assertion.
Shared-database combination is independently asserted by the new concurrency
tests. This is a fixture correction, not suppression of an adversarial failure.

One dispute test constructed "unfinalized" media by deleting its already committed
QC. The monotonic guard now correctly carries that QC forward. Its fixture gained
an optional `finalize_media=False` path, so the negative test uses genuinely
unfinalized media while the existing `raises(ValueError, match="not finalized")`
assertion remains exactly intact. The entire 14-case dispute file then passed.
No erasure bypass was added to production or to that test. The earlier combined
run's 64 passes/one superseded fixture failure is not represented as a green
65-case run: 51 unchanged admission/activation/reporting passes from its XML plus
the complete corrected dispute rerun provide the final 65 distinct passes.

An earlier combined admission run was interrupted when it appeared stalled;
the single-case diagnostic and verbose combined rerun completed. A mistyped
optional selection ran no tests. Neither incomplete/no-test output is counted.
Host runs used the documented TestClient-capable context with workspace TEMP/TMP;
no automatic approval review rejection occurred.

Intermediate new-test failures identified an incorrect SQLite-only fixture
assumption and the existing persisted-proof exception wrapper; both expectations
were corrected to the actual JSON/SQLite setup and existing error contract.
Original negative assertions were not relaxed. Intermediate outputs are not
reported as final passing runs. No full-repository, deployed-node, arbitrary
filesystem power-loss or distributed Byzantine verification is claimed.

Reproduce from the repository root, creating a fresh workspace TEMP/TMP directory
and fresh basetemps before each run:

```powershell
New-Item -ItemType Directory -Force temp/task717e-repeat-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task717e-repeat-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_17e_finality_durability.py tests/test_milestone_7_task_7_17c_finality_audit.py tests/storage/test_task_4_2_native_transaction_records.py -q --tb=short --basetemp=temp/task717e-repeat-focused
.\.venv\Scripts\python.exe -B -m pytest tests/blockchain/test_task_3_5_validator_quorum_finality.py tests/blockchain/test_task_3_6_public_finality_status.py tests/blockchain/test_protocol_v1_lifecycle_finality.py tests/services/test_task_9_consensus_services.py tests/services/test_task_4_7_canonical_reorg_recovery.py tests/integration/test_task_4_7_atomic_reorg_recovery.py tests/integration/test_two_node_consensus_verification.py tests/storage/test_sqlite_storage_backend.py tests/storage/test_json_storage_backend.py tests/storage/test_storage_regression_pass.py tests/integration/test_task_4_5_native_transaction_outbox.py -q --tb=short --basetemp=temp/task717e-repeat-regression
.\.venv\Scripts\python.exe -B -m pytest tests/api/test_chain_sync_api.py tests/api/test_peer_block_sync_api.py tests/api/test_peer_certificate_sync_api.py tests/api/test_peer_vote_sync_api.py tests/blockchain/test_certificate_block_validation.py -q --tb=short --basetemp=temp/task717e-repeat-peer
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_freeze_consistency.py tests/test_protocol_v1_originality_votes.py tests/test_milestone_7_task_7_15_history.py tests/test_milestone_7_task_7_16_atomic.py -q --tb=short --basetemp=temp/task717e-repeat-canonical
```

## 9. Compatibility, remaining critical vulnerabilities and release status

Unchanged: `ceil(2N/3)`, normalized configured validator identities, membership
behavior, EIP-191 signing/message domains, historical v1/v2 block/certificate
formats, block hash preimages, originality fork-choice ranking, active acceptance
on an unfinalized parent, and isolated protocol activation boundaries. No new
finality signature, signer lock, voting round, epoch, proposer election or
proof-synchronization protocol exists. Same-target proof immutability does not
retroactively revoke a QC when more equivocation evidence appears.

Operational differences: stale compatible saves retain finality; unsafe chain
saves fail instead of dropping votes/anchors; exact message retries authenticate
but do not store signature variants; writes/loads are serialized locally; finality
queries with unknown recovery outcome are unavailable; storage errors remain
local failures; active SQLite requires DELETE/EXTRA and closes each connection.
These repairs alter persistence/retry/error behavior, not consensus validity.

Still critical and deliberately unrepaired:

- No distributed agreement, safe signer discipline, durable signer safety state,
  locks or view-change/failover protocol. Conflicting remote commitments remain
  possible under the documented signing/fault assumptions.
- N=3/q=2 still cannot tolerate one equivocator safely; no fault/quorum policy
  correction is silently applied.
- Validator authority remains externally configured; persisted proof lists do
  not establish authenticated historical membership.
- No independent finality proof/authority sync; same-tip chain sync is insufficient.
- Observer-dependent inert proof exclusions, incomplete equivocation knowledge,
  split-vote liveness and no-media reviewer-clock limits remain.
- Reviewer-history event authority/completeness/replay/admission decisions remain
  unresolved; local finality durability does not authorize Task 7.17 to resume.

No consensus-family activation is needed for these local repairs, but no live
rollout is performed or authorized by a passing test count. Review the explicit
DELETE-only operating requirement, error handling and deployment environment
before any separately authorized production rollout. Existing WAL stores must
not be reset or converted implicitly.

**Task 7.17E is ready for review and commit as a local durability repair.** No
commit is created. Final branch and full HEAD remain as in section 1. The final
worktree is exactly the nine files listed in section 3: six modified tracked
files and three new files, all unstaged; the index has no staged changes.

Syntax, local document links, UTF-8/newline checks and `git diff --check` passed.
Source comparison verifies the quorum, attestation validation and proof-validation
functions are unchanged, and signing/domain/isolated WAL-guard source files are
unchanged after checkout line-ending normalization. All 26 original audit-test
assertions and all 35 original two-node-file assertions are retained. The frozen
historical method ASTs match starting HEAD exactly. The dispute's original
unfinalized-media rejection context also matches, with a stronger setup assertion.
Evidence: `temp/task717e-verification.log` and the JUnit reports above.

No subsequent remediation stage is started. Task 7.17 remains blocked; no public
BFT-readiness, distributed agreement or deployment guarantee follows from this
local repair.
