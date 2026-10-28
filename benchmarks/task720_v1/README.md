# Task 7.20 production-like acceptance profile v1.0.0

This is an isolated measurement directory. No v3 activation, production
integration, database access or traffic-distribution claim is made. All newly
authored corpus artifacts are self-created and dedicated to CC0-1.0; no media
was downloaded and no private files were used. Existing frozen fixtures remain
under their existing repository terms. The source-code members are the actual
new `corpus.py` and `measure.py` implementations, plus one short function.

The corpus is deliberately **synthetic/production-like**, not real-world media.
All five permitted MIME types are covered. JSON/code are carried as text/plain.
Text includes short through maximum-size varied operational narratives, nested
event JSON with unique hashes, complete benchmark source and an ASCII entropy
control. Images include tiny, dashboard, noise-texture, near-current-cap and
near-v3-cap objects in each accepted format, plus GIF/WebP animation. The
dimension search uses only original container size (90–100% of the relevant
cap), never compression results. There are no sampled production weights.

From `C:\Users\mattk\ZoidbergChain`, use the existing `.venv` environment:

```powershell
$task720Temp = Join-Path (Get-Location) 'temp/task720-manual'
New-Item -ItemType Directory -Path $task720Temp -Force | Out-Null
$env:TEMP = $task720Temp
$env:TMP = $task720Temp
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -B benchmarks/task720_v1/measure.py --output temp/task720-manual/replay
.\.venv\Scripts\python.exe -B benchmarks/task720_v1/crosscheck.py temp/task720-manual/replay
.\.venv\Scripts\python.exe -B benchmarks/task720_v1/compare.py temp/task720-manual/replay
.\.venv\Scripts\python.exe -B benchmarks/task720_v1/run_tests.py
```

`measure.py` without `--output` writes this directory's new evidence only. It
checks a present reference manifest exactly before proceeding. It never writes
historical evidence. Native encoder/Python behavior is not assumed portable:
hash, version or source drift fails verification. No dependency is installed
or upgraded by these commands. Exact observed versions are in `before.json`;
codec pins are the unchanged root `requirements-benchmark.txt`.

`codecs.json` contains seven native-codec profiles, every per-object byte count,
9 timing observations after 2 warmups, raw/descriptor expansion flags and
category distributions. Comparison-only Brotli and zlib descriptors are size
estimates, not valid v3 representations. The three Zstd profiles use the
existing checksum/content-size/single-thread/no-dictionary/256 KiB-window
settings. Actual adaptive production always uses existing Zstd level 3.

`records.json` contains the complete canonical record's disjoint field ledger,
two-way source-byte trials, actual producer choice, full-record identity
comparison, reconstruction, worker resource measurements, metadata sensitivity
records and invalid/boundary results. The ledger charges every key, colon,
value, quote, brace, comma and wrapper byte exactly once. Nested signatures
and certificates are diagnostic subsets, not additional additive components.
The default fourteen-vote fixture is a fixed comparison scenario, not a measured
traffic distribution. Sensitivities keep the primary population unchanged.

`metrics.json` distinguishes equal-record nearest-rank percentiles/means,
canonical-byte weighted shares and original-byte weighted means. Primary
metadata is `R - base64 payload characters`, so descriptor and framing count;
base64 expansion is reported separately. The stricter `R - encoded bytes`
measure is also in each row. External finality proofs, database/index bytes
and future unapproved journal commitments are outside R and are not zero.

`historical_audit.json` retains all 36 historical objects, original hashes and
sizes, origins, weights and original Zstd behavior. `admission.json` records
current technical-validator outcomes for every new object; rejected capacity
objects remain in the full v3 population. A separate accepted-current subset
is descriptive and never replaces the primary statistics.

`crosscheck.py` independently recalculates arithmetic with the standard library.
`compare.py` compares fresh reproduction against the published reference,
excluding only observed timings/worker process metrics. `run_tests.py` records
bounded commands, exact outcomes and separate platform skips. No unsafe WAL
replay, public API networking, atomic crash or later BFT/journal suite is run.
See the main report for the interpretation and acceptance decisions.
