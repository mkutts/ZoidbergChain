# Task 7.25 v1 — physical storage and transfer evidence

Only the new report and this directory are deliverables. Production code, frozen
corpora/results, network settings and active storage stay unchanged. No commit,
staging, push, migration, WAL, public peers or archival implementation.

Use the existing Windows reference venv from the repository root. No install or
upgrade is needed. Native encoder byte portability is not assumed. This is a
finite synthetic candidate-storage study, not measured production traffic or a
selected/finalized chain. Full original media remain inside each canonical block.

## Reproduce in a new ignored directory

```powershell
.\.venv\Scripts\python.exe -B verification/task725/measure.py --output temp/task725-replay
.\.venv\Scripts\python.exe -B verification/task725/transfer.py --output temp/task725-replay
.\.venv\Scripts\python.exe -B verification/task725/economics.py --output temp/task725-replay
.\.venv\Scripts\python.exe -B verification/task725/run_tests.py --output temp/task725-replay
.\.venv\Scripts\python.exe -B verification/task725/compare.py temp/task725-replay
.\.venv\Scripts\python.exe -B verification/task725/verify.py --check
git diff --check
git status --porcelain=v1 --untracked-files=all
```

Choose a new output path for each replay. Measurement creates a unique disposable
`temp/task725-*` directory. Database files and generated media are not committed.
Fixture generation/signing and repeated recovery can take many minutes. Work is
bounded by frozen corpus membership, sample counts, one network request at a time,
30-second request timeouts, existing decoder limits, 1,200-second fresh recovery
process bounds and 360-second test-group bounds. Reusing an output directory can
overwrite that directory's evidence; never point reproduction at old task folders.

The main measurement refuses changed originals, encoded sizes or exact frozen
canonical record hashes. Repeated storage cycles change only the unsigned header
height and record identity, retaining original media/certificates; they do not
claim independent production content. All normal inserts use inherited V3Store
operations through Task 7.21's existing DELETE/EXTRA initializer. Minimal and
no-secondary schemas are comparison-only disposable SQL stores. The legacy
V3Store initializer/backup verifier enables WAL and is deliberately never invoked.

The local transfer pass needs permission to open a connection to 127.0.0.1 in
restricted Windows execution. If the main pass records WinError 10013, it retains
that outcome and finishes storage/recovery; run `transfer.py` with local connection
permission. The separate command above reuses exact canonical records in the
disposable database without regenerating corpora. The physical test group also
contains a tiny loopback check and needs the same permission. No public addresses
are accepted by either harness.

This reference run completed the full SQLite experiment and permitted transfer,
then continued copies with `measure.py --copies-only` to remove a redundant parent
decoder pass. That mode reuses completed source databases, writes to a new unique
copy directory and proves the source database files stayed byte-identical. Fresh
recovery still uses actual inherited `get` and the real isolated decoder for every
record; the parent performs a separate byte comparison through read-only SQL.
The interrupted development attempt and continuation are recorded, not labeled a
timeout or silently omitted. A fresh ordinary `measure.py` run includes the same
updated copy procedure without needing this continuation option.

`compare.py` requires exact payload hashes, SQLite allocation/page counts, index
accounting, backup/recovery bytes and results on the same reference stack. It
excludes timings and permits only the explicitly checked <=2-byte request-header
variation from an ephemeral port's digit count. No payload-byte tolerance is
allowed. Retrieval timings are warm-cache query/BLOB observations, not full
validation throughput. The physical tests check the selected evidence directory;
existing historical tests continue checking their own immutable reference data.

`verify.py --check` verifies this package's checksum manifest and six historical
manifests without rewriting them. The no-argument form is the author's finalizer:
it requires the original branch, HEAD, index, tracked bytes and allowed untracked
paths, then records preservation/acceptance and freezes checksums. After an owner
commit, that preflight is historical; use `--check` for read-only reproduction.

## Evidence map

| File | Content |
| --- | --- |
| `preflight.json`, `preservation.json` | Initial/final Git state; every preexisting tracked-file hash and unchanged index |
| `environment.json`, `source_versions.json`, `corpus_hashes.json` | Reference stack, actual source boundaries, frozen input identities |
| `workloads.json` | All originals, excluded objects, accepted-byte commitments, raw E, complete R, block hashes and Balanced cap decisions |
| `sqlite.json`, `index_growth.json` | Sample sizes, file/allocation/pages/free pages, marginal growth, separate schema/index accounting at every sample count, constraint and query observations |
| `backup_recovery.json`, `copy_execution.json` | Actual full-copy sizes, observed copy high water, fresh-process identities/original commitments; unchanged source-file hashes for the copy continuation |
| `transfer.json` | Every actual loopback HTTP exchange, separate canonical/body/HTTP/auth bytes and unobserved packet fields |
| `projections.json`, `month36.csv` | 36-month series, all four workloads/three rates/three hosts, historical comparisons and sensitivity cases |
| `*_outcomes.json`, `*_tests.txt`, `tests_execution.json`, `all_test_attempts.json` | Per-node actual results, commands, time bounds, failures/skips/deselections/timeouts; final suite and supplementary repeated attempts separately reconciled |
| `manifest_checks.json`, `checksums.sha256` | Historical and new integrity inventories |
| `acceptance.json` | Separate original-development and production verdicts, exact owner limitations and remaining gates |

Snapshot uses SQLite's consistent online backup API. Full backup and restore use
exclusive, fsynced streaming copies, with separate file identities. Same-volume
copies share a failure domain. Ratios do not imply remote durability or provider
snapshot behavior. Recovery keeps live DB, snapshot, staged backup and restored
DB simultaneously; the model funds both staged and destination copies.

Transfer is **SIMULATED v3** using real existing broadcast/history-fetch wrappers,
requests, HMAC header builder/verifier and Starlette response serialization.
It never registers an active route. Canonical parsing, signatures and isolated
reconstruction are real; chain membership/finality/authority are not established.
ACK response fields are a declared synthetic fixture, not an approved v3 contract;
the real serializer's emitted bytes are counted separately from canonical payload.
No packet overhead, TLS bytes or TCP retransmissions are invented.

Hosting prices are unchanged Task 7.22 illustrative USD assumptions, not current
quotes. Small append-only samples do not measure multi-year fragmentation, real
traffic distribution, retained forks, deeper B-trees, service tiers or future
review-journal/archive overhead. Full-copy backup compression is not credited.
