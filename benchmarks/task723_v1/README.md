# Task 7.23 meme-first sizing study v1.0.0

**PROPOSED / UNAPPROVED / INACTIVE. Milestone 7 remains INCOMPLETE.**
Read the [recommendation](../../docs/milestone-7-meme-first-launch-sizing-recommendation.md).
All new files are isolated here and in that report. Active rules, history,
SQLite, genesis, fixtures, codecs and reviewer policy are untouched.

Use the existing pinned Windows `.venv` from the repository root. No install,
network request, production DB, live services or validator keys are needed.

```powershell
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/run.py
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/enrich.py
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/crosscheck.py
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/tests.py
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/replay.py --output temp/task723-fresh-replay
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/report.py
.\.venv\Scripts\python.exe -B benchmarks/task723_v1/finalize.py
```

The replay directory must not already exist; choose another fresh name under
`temp/` on a subsequent replay. Timings/resource observations are expected to
vary; all other JSON fields, original/encoded/record hashes, byte ledgers,
coverage and economic bills compare exactly. Each subprocess has a 600-second
bound. Full replay logs stay in the ignored replay directory; bounded tails,
commands, durations and comparisons are retained in this package. No historical
measurement is overwritten. Outputs are limited to this package or `temp/`.

`manifest.json` records 59 originals: 58 primary and one predeclared diagnostic.
Two original-size-overflow controls remain in primary admission denominators;
their native codec results are valid, but canonical records/metadata are null
because the unchanged frozen producer cannot construct them. Primary canonical
statistics cover the other 56. Every corpus object can be regenerated locally;
binary originals and signed records are not duplicated in this evidence bundle.
Every regenerated original/encoded/complete-record identity is checked in replay.
Environment versions and all 1,141 preexisting tracked-file hashes are retained
in preflight.json. Native library/encoder drift must fail identity comparison.

Seven native profiles: identity; Zstd 1/3/9, checksum/content size, 256 KiB
window, single thread, no dictionary; Brotli 1/5/9 generic, 256 KiB window.
These are encoder experiments; normal adaptive production remains unchanged
Zstd 3 versus identity. All legal identity/Zstd alternate records are actually
encoded and strict-worker checked, with VALID/INVALID outcomes retained;
native lossless success alone does not establish frozen-profile acceptance.
Brotli complete-record sizes are explicitly
hypothetical descriptor substitutions; Brotli is not a frozen valid codec ID.

`codecs.json` retains 413 exact-byte/hash trials, five repetitions after one
warmup, CPU and wall timings, descriptors/media members and complete records.
CPU uses amortized ~20 ms batches (up to 200,000 calls) to reduce coarse Windows
tick quantization and includes loop/call overhead. `refresh_cpu.py` was used to
replace only initial sub-tick CPU observations, checking all byte/hash data;
normal full reproduction uses the same batched method in run.py.
Python traced peak allocations exclude native arenas/RSS. Strict selected and
alternate worker Job peaks include interpreter/IPC overhead and are separate.
No native per-codec total peak-memory claim is made.

`records.json` retains full disjoint JSON field ledgers and component partitions,
actual producer choice, same-context identity baseline, SHA-256 reconstruction,
current technical admission results and six sensitivity records. Public fixture
signatures are format/crypto evidence only, not chain/reviewer authority.
Metadata is `(R-base64 payload content)/R`, with no evidence subtraction.

`candidates.json` contains five common-image-ceiling comparisons, 100 separate
static/GIF/text-cap scenarios and the three proposed launch profiles. Fractions
are unweighted feature/stress-corpus coverage, never production admission rates.
Full existing security/certificate/transaction budgets are reserved. The static
MIME cap also applies to animated WebP; GIF is a separately explored allowance.

`economics.json` uses the unchanged Task 7.22 full capacity simulator and
illustrative unquoted prices. All 36 monthly partitions are retained for the
36 main scenarios, plus 54 mean-size sensitivities. A common-average control
shows that lowering ceilings alone does not reduce expected bills. Future
review-journal and external proof costs remain separate, unpriced and unapproved.
`crosscheck.py` recomputes identities, ledgers, nearest-rank percentiles,
admission/security bounds and Decimal costs independently of that simulator.

`tests.py` records focused analytical/strict-codec/frozen-v3/current image
admission tests. One exact live-API test ID is explicitly deselected and recorded.
The first default-temp/API attempt was interrupted and earns no complete credit;
the final runner confines all temporary fixtures to a fresh workspace directory.
It does not run live API, production storage or later journal
work. `replay.py` performs fresh complete measurements and exact comparison.
`finalize.py` checks every preexisting tracked hash, unchanged index/HEAD/branch,
only authorized new paths, successful validations and deliverable checksums.
Run it after regenerating the report or other intentional new-package changes.

The synthetic corpus, licensing scope, initial retained capacity-loop failure,
resource-measurement limitations and acceptance failures are disclosed. This
package approves no codec, rewards, new limit, deployment or milestone closure.
