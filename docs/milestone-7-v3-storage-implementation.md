# Milestone 7 Task 7.11 — Isolated Canonical v3 SQLite Persistence and Recovery

Date: 2026-10-19 (America/New_York). Scope: offline persistence primitives and
disposable-database verification only. Protocol v2/block v3 remain inactive.
No active storage, consensus, production, admission, synchronization, migration,
reset or deployment behavior changed. No commit, push, merge or subsequent task.

## Repository verification

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting and ending HEAD: `4cfd6ffbf5eab98fe76ac5c49420f05136c8fef2`.
- Separate prerequisite: `4cfd6ff`, Task 7.10C isolated canonical v3 format.
  Relevant earlier commits: `96db3a0` (7.10B), `ca1ac9e` (7.10A), `824afdb`
  (7.9), `c8d9172` (7.8), `e5a3a77` (7.7).
- Initial worktree clean; canonical modules and 65 frozen golden vectors present.
  No repository/ancestor `AGENTS.md` found. Final changes are new files only,
  unstaged; no historical fixture or active module changed.
- Read the requested storage/capacity, format implementation, canonical schema,
  composition and node economics decisions. Targeted inspection covered
  `storage.py`, `storage_tools.py`, migration/export/backup entry points,
  `CanonicalReorgService`, `FinalityService`, and the isolated finality/codec APIs.
  Existing storage uses atomic document/section replacement; reorg callers select
  the winning history and protect persisted quorum finality. Those active paths
  are unchanged. Their JSON snapshot/file-copy procedures are not reused here.

## Files and isolation

| File | Purpose |
| --- | --- |
| `canonical_v3/storage.py` | Explicit-path, explicit-context `V3Store`; schema, verification, transactions, lookups, selection, proofs, rebuild, integrity, backup/restore/checkpoint |
| `tests/test_milestone_7_task_7_11_storage.py` | Focused disposable-store, worker, failure-injection and process-death tests |
| `scripts/milestone_7_task_7_11_storage.py` | Reproducible original-corpus and golden-record measurement; temporary DBs only |
| `benchmarks/milestone_7_task_7_11_results.json` | Machine-readable measurements, provenance, per-record hashes, comparisons and limitations |
| `benchmarks/milestone_7_task_7_11_focused.txt` | Focused format/storage/codec verification output |
| `benchmarks/milestone_7_task_7_11_regression.txt` | Historical protocol/finality/SQLite/export-import regression output |
| `benchmarks/milestone_7_task_7_11_head_baseline.txt` | Same historical selection against an unchanged-HEAD archive in `temp/` |
| This document | Schema, operations, results, boundaries and remaining risks |

There is no factory registration, implicit filename, active module import,
environment activation switch or dependency change. Initialization exclusively
creates a new file. Existing files must match the exact schema, application ID,
schema version, frozen context and trusted anchor. An empty existing file,
current v1/v2 database, unknown schema or context mismatch is refused, with no
migration or repair-on-open. SQLite replays its own committed WAL on reopen;
opening alone does not replace the full application integrity scan.

## Schema and identity

Schema version **1** is independent of protocol version. SQLite application ID
is `0x5A563331`; foreign keys, WAL, `synchronous=FULL`, a five-second busy timeout,
and explicit checkpoints are used. Automatic checkpoints are disabled for these
offline primitives/measurements; production needs a bounded maintenance policy.

| Table | Stored fields and authority |
| --- | --- |
| `blocks` | `hash TEXT PRIMARY KEY`, `canonical BLOB NOT NULL`; `WITHOUT ROWID`. Exactly one immutable R per candidate, 1..3,145,728 bytes, SQL BLOB type enforced |
| `block_index` | Block hash FK/PK, height, previous hash, original-media SHA-256; all derived from verified R |
| `transaction_index` | Block FK, native transaction position and authenticated `tx_id`; PK `(block_hash,position)`; no transaction-body duplicate |
| `canonical_chain` | Mutable selected height-to-hash map, unique hash/FK; derived from retained selected tip and canonical ancestry |
| `finality` | Target hash FK/PK, exact bounded canonical proof BLOB, bounded canonical trust-context BLOB containing externally authenticated historical validators and equivocators |
| `settings` | One row: exact context, trusted anchor height/hash, mutable selected tip FK; retained local selection metadata |

SQL triggers prohibit UPDATE/DELETE of blocks and retained finality evidence.
These protect normal application use; they cannot protect a database from an
attacker able to rewrite its file, drop triggers or replace all local state.
Finality is outside R and never changes canonical bytes.

Block identity remains `SHA256(J(block envelope))`, exactly as in Task 7.10C.
The wrapper `R=J({envelope,hash})` is retained verbatim, not parsed and reencoded
on write. No file hash, row ID, storage checksum or original-media hash becomes
an alternative block identity. SHA-256 of reconstructed original M remains media
identity. No external media storage, decoded-original table, second chain JSON,
extra base64 layer, local codec or compressed database wrapper is introduced.

### Index choices and rebuilding

Four explicit secondary indexes cover candidate height, predecessor, original
media hash and native transaction ID. Hash lookup uses primary keys; canonical
height uses the mapping primary key. The predecessor index supports finding
children/competing branches; ancestry walking itself follows hash primary keys.
Original-media/transaction indexes are nonunique across candidates: storage does
not invent consensus uniqueness rules or reject competing histories. The only
legacy transaction is the frozen reward projection, which has no canonical
transaction ID; no local reward ID is invented. No payload, caption, certificate,
signature, profile, size or duplicated transaction-body index is retained.

Finality targets use the proof primary key. Status is derived by checking a
candidate's membership in the selected path at or below the highest retained
proof; ancestors of a finalized target are protected. No redundant mutable
`is_finalized` flag or separate height/finality index needs synchronization.

Block and native transaction projections can be rebuilt entirely from validated
R records. Canonical membership additionally needs **retained selected-tip and
anchor metadata**. Blocks and finality proofs alone cannot determine an
unfinalized winner; rebuilding never performs fork choice. Proof verification
also needs retained, externally authenticated historical trust inputs. Neither
deleted selection metadata nor missing finality authority is guessed from a
proof's self-declared validator set.

`rebuild_indexes()` validates source records, retained selected ancestry and
proofs, then replaces derived rows within one `BEGIN IMMEDIATE` transaction.
Invalid source bytes or unavailable decoding abort and preserve prior rows.
It repairs damaged projection values/missing rows, not physically destroyed
SQLite pages, unknown schema, lost canonical records, tip or proof evidence.

## Validation, error classification and transactions

`insert(raw)` first applies the existing strict parser: canonical UTF-8 JSON,
closed schema, complete/component limits, block hash, signatures and internal
bindings. It reconstructs media only through `IsolatedDecoder`; count, checksum,
complete consumption, original SHA-256 and canonical text checks remain intact.
All encoded media stays inside R. Received records are never recompressed.

Format/media validity does **not** prove ledger balances/nonces, ancestry time,
historical eligibility/snapshot completeness, image safety, reward claims or
complete consensus validity. A later authorized caller must establish those
before selecting or finalizing. Candidate insertion is not canonical acceptance.

| Situation | Result |
| --- | --- |
| Incoming malformed canonical record | Existing `V3Error`; nothing written |
| Incoming deterministic media rejection | `MediaRejected` retaining INVALID `Outcome`; nothing written; not a claim of complete consensus adjudication |
| Worker resource/startup/cancellation/local failure | `StorageUnavailable` retaining INDETERMINATE_LOCAL_FAILURE; no retry as identity and no invalid-media classification |
| Stored malformed bytes, hash/key/derived mismatch or deterministic failed media integrity | `StorageCorruption`, a local storage error; never consensus-invalid media |
| SQLite lock/busy/disk-full/read-only/I/O failure | Local storage failure; withhold success and roll back |
| Exact hash/byte duplicate | `False`, after rechecking retained bytes/indexes; no second copy |
| Same hash with different retained bytes or conflicting retained proof/context | `RecordConflict`; preserve existing record; no replacement/upsert |

New canonical bytes and all block/native projections commit together before
`insert` returns True. Selection atomically swaps the complete canonical map
and selected tip. Proof insertion is its own atomic evidence transaction. Every
exception, including interrupted rebuild/selection, rolls back the transaction.
Reads use one consistent SQLite snapshot. There is deliberately no ledger,
claims or mempool state here; future acceptance must include them in a shared
transaction rather than assume these separate primitives already provide that.

`get(hash)` verifies stored bytes and derived rows; `get_by_height(height)`
verifies selected ancestry/membership. Candidate height, predecessor, original
hash and native-ID lookups verify returned records. A damaged index that omits
a result requires the full `check_integrity()` scan to discover it; a lookup
cannot prove completeness. Length/type is checked before fetching a stored
BLOB. The integrity scan combines schema/context/version checks, SQLite
`integrity_check`, `foreign_key_check`, every record's format/hash/media checks,
complete projection counts/content, selected ancestry and retained proof checks.
The physical-bit-flip test demonstrates why SQLite's `ok` alone is insufficient.

## Chain selection, reorganization and finality

`select_chain(tip, expected_tip=...)` is a storage compare-and-swap, without
longest-chain/work scoring or a new finality algorithm. Callers choose the
winner. Its verified hash-linked path must have consecutive heights back to
the explicit anchor. An empty selection is allowed only without retained
proofs. Missing ancestors, stale tips and finalized-history replacement reject.
All candidate bytes survive branch changes unchanged. Reopen sees either the
old or complete new selection, never a committed partial path.

The default anchor is height zero and the explicit context's genesis hash;
the non-genesis parser does not construct/store a genesis record. An explicitly
provided nonzero anchor models a later authenticated snapshot boundary, not an
assertion that storage authenticated the snapshot or all its prior history.

`finalize` validates the existing v3 proof schema/signatures and unchanged
`ceil(2*n/3)` quorum, sorted unique trusted validators, equivocation exclusions,
network and exact selected height/hash. The caller supplies trusted ancestry
inputs; a proof's embedded set is never automatically trusted. Retained proofs
and inputs are revalidated on integrity/rebuild/selection. Replacing any
ancestor of a retained finalized target is prohibited. Complete active finality,
equivocation ingestion, state replay and reorganization integration are deferred.

## Backup, restore and recovery

Use `store.backup(new_path)` while the database is open. It holds a verified
read snapshot and uses SQLite's supported **online backup API**, including
committed WAL data, then opens/verifies the destination independently. A writer
may commit newer source data during backup: the destination still contains the
verified snapshot. Destination connections are explicitly closed; SQLite's
transaction context manager alone does not close them on Windows.

`V3Store.restore(source,new_target,ctx,...)` validates the source and performs
the same online backup into a new path. Source must exist; neither backup nor
restore overwrites an existing target. Retain the original context and anchor.
After restore, run `check_integrity()`; use `rebuild_indexes()` only for damaged
derived rows backed by intact records/evidence/selection metadata. Never infer
missing original media from an unverified cache. No live WAL file-copy backup
procedure is implemented or recommended.

An interrupted backup may leave a partial/empty destination. Treat it as failed,
do not publish/promote it, and require independent verification before use.
The test interrupts SQLite after its first copied page, confirms the source is
unchanged and restoration refuses the incomplete result. There is no automatic
promotion/replacement of a live database or automatic deletion of failed files.

Tests force dirty pages into WAL with a one-page cache, then terminate the
process without closing connections: uncommitted insertion rolls back and
committed insertion survives. Another process dies after deleting the old
canonical map but before installing its tip; restart retains the old complete
selection. Exception injection covers block/index, reorganization, finality and
index-rebuild boundaries. A held reader yields a busy checkpoint result; releasing
it permits `wal_checkpoint(TRUNCATE)` to zero WAL without losing exact records.
Missing selected ancestors, malformed BLOBs, damaged evidence/indexes, invalid
database headers and an actual canonical-byte bit flip are detected. Lost
canonical records need a known-good backup or later fully verified peer recovery.

## Measured storage

Source: [machine-readable results](../benchmarks/milestone_7_task_7_11_results.json).
Windows CPython 3.13.5, SQLite 3.49.1, zstandard 0.25.0; 4,096-byte pages, WAL,
FULL synchronization. Each BLOB insertion is independently committed. Golden
fixtures retain three competing height-one records, including a native transfer
reference per record. The corpus has 36 selected records and no native transfers.

The corpus generator checks all original byte hashes against the existing
deterministic manifest, then produces freshly signed closed-schema evidence in
the existing symbolic fixture context with public test scalars. Seven trailing
text bytes are removed by explicit canonical text normalization; image bytes are
unchanged. These are format/crypto/media fixtures, **not accepted chain history**
or live image-admission evidence. The unchanged nonce-one golden native transfer
is not repeated through the 36-record chain. Original/media/record hashes are
recorded per row. Golden vectors are read without regeneration.

| Quantity, bytes | Corpus, 36 blocks | Frozen vectors, 3 blocks |
| --- | ---: | ---: |
| Exact canonical R / stored BLOB total | 8,241,301 | 103,777 |
| Empty database after checkpoint | 49,152 | 49,152 |
| Main DB before checkpoint | 49,152 | 49,152 |
| WAL before checkpoint (including selection) | 9,377,152 | 210,152 |
| Main DB after checkpoint | 8,376,320 | 159,744 |
| WAL after checkpoint | 0 | 0 |
| Main DB after VACUUM + checkpoint | 8,372,224 | 159,744 |
| Consistent backup file | 8,376,320 | 159,744 |
| VACUUM WAL before truncation | 8,421,312 | 160,712 |
| SHM while open | 32,768 | 32,768 |
| Logical block-index value widths, excluding SQLite encoding/pages | 7,200 | 600 |

Corpus totals: original M **6,093,910 B**, encoded E **5,285,229 B**, retained
base64 payload characters **7,047,024 B**; 26 zstd and 10 identity selections,
36 distinct original hashes. Storing JSON in a BLOB **does not remove base64
expansion**. The post-VACUUM DB is 130,923 B above R (1.589% including the empty
schema, row allocation, identifiers and all indexes); this is not isolated index
cost. `dbstat` is unavailable in this SQLite build: separate physical
table/index attribution is unknown (`index_bytes:null`), not zero. Primary keys
of WITHOUT ROWID tables are part of those tables' B-trees.

Each block has one canonical media representation; no decoded-media, native-body
or chain-section duplicate is retained. Competing blocks intentionally retain
their own authenticated media: the three golden records share one original hash
but distinct block commitments. WAL/SQLite page versions, backups and VACUUM
workspaces are physical additional copies, not eliminated duplicates.

Observed corpus WAL peak at the reported observation points is 9,377,152 B.
Backup adds 8,376,320 B. A conservative one-main-DB VACUUM work allowance adds
another modeled 8,376,320 B: **26,129,792 B additional planning headroom**, plus
SHM and filesystem margin. The simultaneous filesystem temporary-file high-water
mark was **not measured**. This allowance is modeled, not a measured minimum or
maximum. VACUUM size is measured after a final checkpoint; the transient WAL is
reported separately. There is no filesystem compression/dedup assumption.

### Comparison with Task 7.7

| Layout/workload | Logical serialized bytes | Post-checkpoint DB | Post-VACUUM DB | Observed pre-checkpoint WAL |
| --- | ---: | ---: | ---: | ---: |
| Task 7.7 projected v3, old current JSON-section engine | 7,621,402 chain JSON | 10,551,296 | 7,929,856 | 10,728,512 |
| Task 7.11 closed v3 canonical BLOB rows + indexes | 8,241,301 R | 8,376,320 | 8,372,224 | 9,377,152 |
| Task 7.11 identical R objects in a minimal JSON section | 8,241,338 chain JSON | 11,132,928 | 8,261,632 | 11,433,032 |

Task 7.7 measured 7,602,184 projected **envelope** bytes; the normative portable
wrapper correction is 36*87=3,132 B, yielding 7,605,316 B before other schema
changes. Task 7.11 uses closed signed evidence, exact rational fields, a different
fixture context/transaction mix and canonical text. Its post-VACUUM DB is
**442,368 B larger** than the historical projection; that is a measured workload
difference, not a pure BLOB storage effect or a promised saving.

The same-R control uses a minimal one-section table, no active schema, and four
whole-section saves at 1/5/15/36 records. It holds identical canonical objects,
without an escaped JSON-string/base64 wrapper. The indexed BLOB DB is **110,592 B
larger after VACUUM**, while its observed append WAL is **2,055,880 B smaller**
for these different, explicitly stated update sequences. This is evidence about
allocation/index and write patterns, not proof that SQLite BLOB outperforms TEXT
as a storage class, production throughput or a universal WAL advantage.

No small-fixture result is extrapolated to millions of blocks. Task 7.8's
economics inputs, physical amplification, temporary space and backup assumptions
are unchanged. Large-scale retained branches, long-lived readers, fsync latency,
index distribution and growth, metadata lifecycles, caches and sustained load
remain unmeasured.

## Reproduction and verification

Run from the repository root; use writable repository-local test directories.
All actual databases are temporary, and production databases are never read,
modified or reset.

```powershell
.\.venv\Scripts\python.exe -B scripts/milestone_7_task_7_11_storage.py
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_11_storage.py tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py -q --tb=short -p no:cacheprovider --basetemp=temp/task711-review
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds tests/storage/test_sqlite_storage_backend.py tests/storage/test_storage_tools.py -q --tb=short -p no:cacheprovider --basetemp=temp/task711-review-regression
```

The historical regression selection yields **92 passed, 23 failed**. Every
failure rejects the unchanged `zoidberg.jpg` at existing technical image
admission with `MALFORMED_MEDIA`, before its storage workflow. The same selection
in a temporary archive of unchanged HEAD reproduces **the identical 23 failing
node IDs and 92 passes**. Both detailed outputs are retained above. Historical
protocol/golden/native/quorum cases pass; existing image-dependent export/import
and end-to-end storage workflows remain a baseline environment limitation.
No admission bypass or unrelated fix is included. The full repository suite and
native Ubuntu deployment tests are not claimed.

Final focused result: **354 passed** in 100.38 seconds: **53** new storage tests,
**119** existing v3 format tests and **182** existing codec/sequence tests.
The complete measurement ran twice successfully with byte-identical JSON
SHA-256 `33750a785afbcd8e0808ec04b3f38b1a2fe931c6e2f40f0e7de4c65510e8c86e`.
This repeats the measured fixture results on this environment; it is not an
independent implementation or native Ubuntu verification. Whitespace, local
report links, unchanged tracked source/fixtures, empty staging area and unchanged
HEAD were checked separately.

## Production boundaries and remaining risks

| Later connection | Required work; none connected here |
| --- | --- |
| Active block production | Fully validate frozen snapshots/state, pack exact R budgets, share canonical bytes with acceptance transaction |
| Consensus validation | Trusted launch identity, state/nonce/balance/claim checks, image safety and historical evidence authority; withhold action on local decoder/storage failure |
| Finality | Authenticate historical validator/equivocation inputs and target ancestry; collect new-domain proofs and durable external finalized checkpoints |
| Reorganization recovery | Atomically replay ledger, rewards, native lifecycle, uniqueness/reviewer/evidence claims with selected mapping/tip; no separate-map-only integration |
| Peer synchronization | Bounded paging/transport, complete verification before commits, resume/checkpoint and missing-record recovery tied to trusted head/finality |
| Export/import | Versioned bounded stream retaining exact R, context/anchors/proofs/trust inputs; staged validation, atomic publication and portable-reader tests |
| Media retrieval | Verified original M/H/length/MIME plus full admission policy; no response media on local failure and no external-store dependency |
| Database migration/reset | Explicit later authorization, inventory/disposition and verified old backup; never silently transcode/re-sign old history or open current DB as this schema |
| Launch/genesis activation | Actual owner-approved N/W/G, registry/policy/genesis/validator freezes, independent audit, deployment rehearsal and explicit activation authorization |

These primitives intentionally scan/materialize full selected ancestry during
selection, height lookup and integrity work. Lookup results and all-candidate
scans are not bounded production synchronization APIs. Candidate retention,
incremental verified checkpoints, batch/range limits and resource/lock budgets
need a separate integration design and measured load tests. Synchronous decoding
inside read/write transactions can hold locks for substantial time. No durability
claim is made against broken fsync/storage hardware or power loss beyond SQLite's
documented transactional model; tests terminate processes, not a physical device.

Schema validation, hashes and triggers do not authenticate mutable local tip or
externally supplied trust authority against an attacker controlling the entire
DB. A wholly deleted unselected candidate or wholly deleted proof cannot be
discovered from remaining records alone without an external expected inventory
or finalized checkpoint. Intact retained evidence prevents ordinary API-driven
finalized-history replacement. Corruption is detected, not magically repaired;
known-good backups and independent trusted recovery sources remain necessary.

Independent decoder/verifier/security review, worker filesystem/network/privilege
confinement, aggregate resource limits and native target-service validation from
Tasks 7.5/7.6 remain release gates. This task preserves the worker boundary and
three-state outcomes; it does not close those gates or the existing image-admission
environment failure. These are production blockers, not permission to activate.

Task 7.11 is **ready for review and a later user-controlled commit as isolated
storage work**, with the recorded baseline and production limitations. No
production cutover or complete reorganization integration is claimed.
