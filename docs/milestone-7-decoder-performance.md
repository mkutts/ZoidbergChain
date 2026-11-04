# Milestone 7 Task 7.6B — Strict decoder performance and resource safety

Status: isolated optimization and resource investigation; production security approval remains blocked. Date: 2026-10-18. Scope is limited to prototype verification, measurements and a worker-isolation design. No active blockchain, validator, admission, block-format, storage, API or sync code changes; no reset, bounty, codec registration, commit, push, merge, deployment or subsequent task implementation.

## Baseline and reproduction

Verified branch: `Compression-State-Bloat-and-Node-Economics`. Starting/final HEAD: `723a37a6627650213c9ee78ca787086b3f2659f9`, separately committed Task 7.6A. Initial worktree clean. Read the [security contract](milestone-7-codec-security-contract.md), [conformance report](milestone-7-decoder-conformance.md), strict adapter/sequence verifier, frozen fixtures, tests and Task 7.6A measurements. Repository inspection was limited to those materials and available decoder tooling. No applicable agent instructions were found in the previously inspected repository guidance directory.

Before editing the verifier, the Task 7.6A runner reproduced 152 golden outcomes (42 accept, 110 reject) and 36/36 byte-exact Zstd corpus reconstructions. Its output/log are retained in ignored `temp/task76b-reproduced-76a.json` and `temp/task76b-baseline-reproduction.txt`. An initial maximum-match run measured 1.778 seconds before versus 0.489 seconds after; those exploratory samples are not the final controlled comparison.

Current evidence is [`benchmarks/milestone_7_task_7_6b_results.json`](../benchmarks/milestone_7_task_7_6b_results.json). The [runner](../scripts/milestone_7_task_7_6b_performance.py) reads the original adapter/verifier directly from the fixed local Git commit above, records their hashes, loads them in an isolated benchmark namespace, and compares them with current code. It does not fetch code or register arbitrary codecs. The old vectors, manifests, historical results, dependencies and protocol contracts remain unchanged.

Toolchain: CPython 3.13.5, Windows 11 AMD64, zstandard 0.25.0 / libzstd 1.5.7, CFFI 2.0.0. No new native dependency or package was installed. Five measured repetitions follow one warmup; before/after order alternates each repetition on identical M/E/descriptor inputs. Raw elapsed/process CPU samples, median, nearest-rank p95 and worst observed time are stored. With five samples, p95 equals the observed maximum: this is a small local sample, not an estimated population-tail guarantee. Windows process CPU values are coarse and often zero for short operations.

Timing reproducibility is limited on this host. A fresh current-code comparison measured 1.710 seconds before and 0.473 seconds after, while a separate repeated-call diagnostic reached median 10.296 seconds before and 3.283 seconds after. CPU time also increased; this was not solely elapsed waiting. The cause of the runtime shift was not established. Final paired data below retains the observed sustained-run values; the faster exploratory measurements must not be substituted for them or used as a deployment budget. Supported-platform repeatability remains outstanding.

```powershell
# Baseline reproduction, performed before optimization:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6a_conformance.py --output temp/task76b-reproduced-76a.json > temp/task76b-baseline-reproduction.txt 2>&1

# Controlled paired measurements, including profiling and memory probes:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6b_performance.py > temp/task76b-final-performance.txt 2>&1

# Exact full focused + adjacent regression command:
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py tests/test_milestone_7_task_7_6b_performance.py tests/test_milestone_7_task_7_3_corpus.py tests/test_milestone_7_task_7_4_benchmark.py tests/test_milestone_7_task_7_4a_image_evaluation.py tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime -q --tb=short > temp/task76b-regression.txt 2>&1
git diff --check
```

The before/after comparisons exclude fixture generation, compression, imports, profiling, tracing and report writing. All 46 main-case timing groups run before any allocation-tracing or profiling diagnostics; an investigation run interleaving those diagnostics was discarded after later cases slowed unexpectedly. No causal attribution for that process-history effect is claimed. Corpus samples are regenerated and byte-hashed against the existing manifest; positive vector fixtures are replayed without recompression. The benchmark also covers high expansion, maximum table sizes, all 699,050 permitted matches, 64 tiny/empty blocks, 64 blocks repeatedly rebuilding maximum tables, and a 65,536-match budget scenario. No timing result determines acceptance, and the tests contain no flaky speed thresholds.

## Profiling findings and changes

The baseline maximum-match profile made approximately 9.09 million calls: 4,194,300 reverse-bit reads, 4,194,351 `int.from_bytes` calls and 699,050 `max` calls. RLE tables consume zero bits for many state/symbol fields, but baseline `read(0)` still sliced a buffer and converted it to an integer. The sequence loop also built temporary row/repeat lists, used `zip`/list comprehensions and allocated tuples to iterate the three state updates. These costs scale with match count even when the frame expands only about twelvefold.

Changes are limited to [`codec_prototype/sequence_verifier.py`](../codec_prototype/sequence_verifier.py):

- Retain width and remaining-bit checks, then return zero directly for a zero-bit read.
- For reads of 1–8 bits, index one or two bytes instead of creating a view slice and converting it. Reads of 9–31 bits retain the bounded conversion path. Bit position, stop flag, exact stream exhaustion and overrun behavior are unchanged.
- Use scalar FSE states and direct row lookups; bind bit-reader and immutable length tables once per block/frame.
- Use three scalar repeat offsets with explicit rotations; preserve every repeat-code/zero-literal special case.
- Unroll the three state updates in the same LL/ML/OF order; update maximum distance with an inline comparison.
- Release cached row references at each block end so an old table set is not retained while the next block rebuilds its tables. A 64-block maximum-table rebuild probe covers this lifetime boundary.

No sequence/output/window/history/table check is removed. Native reconstruction, its fresh static context, exact output capacity, checksum/consumption checks, per-block verifier/native agreement and original SHA-256 verification are untouched. The accepted grammar, maximum sequence count, 64-block ceiling, W and candidate A/B limits are unchanged. There are no contract amendments.

The optimized maximum-match profile retains all 4,194,300 bit-reader calls, but reduces integer conversions to 51 and removes the per-sequence `max` calls. FSE table construction and native Huffman decoding were not rewritten; they were not the dominant maximum-match cost. A future audited native verifier could remove Python dispatch overhead, but must implement the same checks, reproduce these vectors and pass independent review; unaudited native speedups are not introduced here.

## Stage measurements and before/after results

The runner measures descriptor schema/base64 validation (`_payload`), complete frame/header/block preflight, sequence verification, native reconstruction without digest computation, standalone output SHA-256 verification, and total `decode(dict)` validation separately. Canonical JSON transport parsing (`parse_descriptor`) is outside this API measurement and adds bounded work at a raw-wire boundary. It also measures the inline output/window/history predicates using a benchmark-only AST-instrumented copy of each verifier. Every predicate remains present. The copies' output/work counters are checked against uninstrumented results.

Clock probes perturb the loop. Consequently, predicate timing and the parsing remainder are diagnostic distributions; the remainder includes probe overhead. Stage medians must not be summed to claim exact end-to-end latency. The no-digest native copy is benchmark-only and is never an acceptance path; full public validation always verifies SHA-256.

Final total validation times are in milliseconds. Each cell is **median / p95 / worst** from five measured samples. Cases span the host's runtime shift; comparisons within each paired case are more useful than comparing absolute times across cases.

| Input | Committed 7.6A | Optimized |
| --- | ---: | ---: |
| Small ordinary JPEG (`jpeg-flat-small`) | 0.127 / 0.130 / 0.130 | 0.084 / 0.087 / 0.087 |
| Medium mixed JPEG | 6.037 / 6.602 / 6.602 | 4.089 / 4.596 / 4.596 |
| Photo JPEG (`jpeg-photo-small`) | 94.903 / 97.677 / 97.677 | 50.098 / 55.967 / 55.967 |
| Capacity/photo JPEG (`jpeg-photo-like`) | 129.691 / 766.127 / 766.127 | 63.586 / 407.640 / 407.640 |
| High-entropy capacity PNG | 54.286 / 54.897 / 54.897 | 52.418 / 54.554 / 54.554 |
| Capacity GIF | 26.213 / 28.574 / 28.574 | 26.959 / 27.293 / 27.293 |
| 43,690 short matches | 643.509 / 658.132 / 658.132 | 202.460 / 210.941 / 210.941 |
| 699,050 short matches, full A | 10,085.670 / 10,213.525 / 10,213.525 | 3,309.205 / 3,360.072 / 3,360.072 |
| Candidate 65,536-match frame | 950.596 / 967.745 / 967.745 | 304.890 / 316.626 / 316.626 |
| One raw block | 0.147 / 0.193 / 0.193 | 0.144 / 0.156 / 0.156 |
| 64 tiny raw blocks | 1.075 / 1.180 / 1.180 | 1.115 / 1.322 / 1.322 |
| 64 mostly empty blocks | 0.711 / 0.933 / 0.933 | 0.735 / 0.817 / 0.817 |
| 64 blocks, 189 rebuilt maximum FSE tables | 98.763 / 101.785 / 101.785 | 101.614 / 103.517 / 103.517 |
| Highly compressible 2 MiB, 87-byte E | 7.248 / 8.755 / 8.755 | 6.509 / 7.534 / 7.534 |

The sustained maximum-match total median improves **3.05 times (67.2% less elapsed time)**. Its uninstrumented sequence-verifier medians are **10,025.242 → 3,260.620 ms**. Maximum-frame median process CPU time is **9,562.5 → 3,078.125 ms**; the candidate 65,536-match frame uses 281.25 ms after optimization. These are measured observations, not CPU-time ceilings.

There is no universal speedup: observed total medians for capacity GIF, 64 tiny blocks, 64 mostly empty blocks and repeated maximum-table rebuilding increase by about 2.8%, 3.7%, 3.4% and 2.9%, respectively. They are retained in the evidence. Most work on those paths is unchanged; these small-sample results do not establish either a stable regression or improvement. The corpus aggregate, computed as total source bytes divided by the sum of per-case median decode times, is 13.694 → 19.644 MB/s. This synthetic in-memory metric excludes wire JSON parsing, scheduling and integration costs and is sensitive to the nonstationary runtime.

Maximum-match stage observations (current code, milliseconds):

| Stage | Median | p95 / worst |
| --- | ---: | ---: |
| Descriptor schema/base64 | 4.227 | 4.515 |
| Frame/header/block preflight | 0.060 | 0.208 |
| Native reconstruction and result copy, without SHA-256 | 45.107 | 47.375 |
| Standalone output SHA-256 verification | 2.987 | 3.369 |

Diagnostic separation of the same maximum-match verifier (milliseconds, median / p95 / worst):

| Instrumented phase | Committed 7.6A | Optimized |
| --- | ---: | ---: |
| Actual inline output/window/history predicates | 812.761 / 838.404 / 838.404 | 544.305 / 581.220 / 581.220 |
| Parsing/state work plus probe overhead | 10,501.009 / 10,682.486 / 10,682.486 | 3,061.222 / 3,228.925 / 3,228.925 |
| Whole instrumented verifier | 11,313.800 / 11,520.890 / 11,520.890 | 3,607.939 / 3,810.145 / 3,810.145 |

The JPEG capacity sample visibly crosses runtime regimes: its sequence-only medians, measured later, are 737.579 → 399.343 ms, exceeding its earlier total medians. This is additional evidence that phase results cannot be summed or interpreted as a stationary decomposition. Maximum-match paired results are substantially more consistent within their own samples. No portable latency target is approved from this run.

Malformed probes retain identical error stage/code. Median rejection microseconds before/after are 354.3/357.2 (actual offset beyond W), 181.5/172.5 (checksum), 103.9/104.2 (FSE zero-run overflow), 27.0/23.3 (sequence count beyond output), and 24.9/24.6 (missing stop bit). These supplemental samples occur after resource diagnostics and are not included in the main-case timing tables.

## Resource interpretation and remaining amplification

The verifier already streams sequence metadata from bounded views rather than retaining an array of all matches. This design is preserved. Repeat offsets and FSE states occupy constant scalar storage; at most 64 predicted block sizes and the profile-bounded tables are retained. No frame-sized integer, output-sized verifier scratch or sequence-count-sized list is introduced. Removing temporary objects reduces allocation churn; it does not imply a large reduction in peak memory or a portable process-memory ceiling.

Native context remains a fixed 95,968-byte caller-owned static arena, independently reported by `ZSTD_sizeof_DCtx`. Benchmark wrappers observe the CFFI arena and exact M-sized native output allocation; they do not intercept every native allocation or measure stack/RSS. The pinned [static-context API](https://github.com/facebook/zstd/blob/v1.5.7/lib/zstd.h) specifies no resize/malloc for the static context. This supports the measured build's context accounting, not a portable whole-process guarantee.

For A=2 MiB, native output capacity remains 2,097,152 bytes. Copying the verified buffer into immutable Python bytes temporarily retains 4,194,304 decoded-storage bytes, plus the arena, bounded E/base64/descriptor storage, interpreter, tables and allocator overhead. The descriptor's base64 round-trip check and the result copy remain intentional integrity/canonicalization costs. A borrowed native result could reduce copying only by introducing a new ownership/lifetime API, which is outside this optimization.

Python `tracemalloc` probes measure verifier-only allocation peaks separately from timing. A diagnostic run tracing the full 699,050-match case was stopped because instrumentation was excessively intrusive on this Windows runtime; it was not a validation failure. The final harness does not trace cases above 4,096 sequences (a local measurement-work budget, not an acceptance limit). Full maximum-match timing, profiling, CPU, golden and native arena/output tests remain present. Smaller match workloads and 64 maximum-table rebuild blocks are traced. Traces exclude native output/arena, some reused allocations, process baseline, allocator arenas and native stack. Measured Python peaks are observations, not consensus validity rules or proofs of native working memory. No production worker memory cap, native malloc audit, process RSS bound or exhaustive malformed-path CPU proof is claimed.

| Verifier-only probe | Traced peak bytes before | Traced peak bytes after |
| --- | ---: | ---: |
| 128 short matches | 1,494 | 1,268 |
| One maximum-table sequence | 36,984 | 36,896 |
| Highly compressible full-A output | 2,148 | 2,100 |
| 64 blocks rebuilding maximum tables | 50,360 | 50,256 |
| 43,690 and 699,050 matches | Not traced | Not traced |

The repeated-table probe constructs 189 tables / 80,640 total cells over 63 compressed blocks; that is cumulative work, not simultaneously live table storage. Its peak remains close to the committed verifier after explicitly releasing cached row arrays at each block boundary. The modest measured peak changes support an allocation-churn optimization, not a large whole-process memory reduction.

The 699,050-sequence ceiling is finite but still permits substantial CPU work. High ratio alone is a poor proxy: the 87-byte/2 MiB repeated-byte frame has one sequence, while the maximum-match frame uses 174,975 encoded bytes, 699,050 matches and 18 blocks. The latter dominates Python verification despite a much lower expansion ratio. Fragmentation remains an independent overhead, and malformed entropy/native error paths still require reviewed bounds and fuzzing.

The report includes **corpus-only** tighter-budget scenarios. A new sequence cap can be counted deterministically, but adopting it would narrow the accepted profile and requires separate protocol/version review, real-world workload evidence and new boundary vectors. An operator must not turn a local CPU preference into consensus rejection. No tighter cap is selected here.

| Candidate restriction | Corpus samples excluded |
| --- | --- |
| 32,768 sequences | `jpeg-photo-like` |
| 65,536 sequences | None of 36 |
| 32 blocks | `jpeg-photo-like`, `gif-noise-capacity` |
| 48 blocks | `jpeg-photo-like` |
| 1 MiB A/B | `jpeg-noise-capacity`, `png-noise-capacity` |
| Current 699,050 sequences / 64 blocks / 2 MiB A/B | None of 36 |

The 65,536-sequence candidate reduces the theoretical permitted loop count by about 10.7 times and is exercised by its own valid frame. Passing this small corpus is insufficient evidence to adopt it: five corpus originals are already oversized for the separate 1 MiB meme launch policy, and this experiment does not change or re-evaluate that policy.

## Concrete worker-isolation design for separate implementation

Worker isolation is deliberately not implemented as a partial process wrapper. Correct Windows/Linux memory enforcement, privilege removal, native-crash containment and cancellation need dedicated platform tests. A spawned Python process alone is not a security sandbox, and returning after a timeout does not ensure the native operation stopped.

Proposed implementation contract:

1. The coordinator creates an immutable job containing a unique job ID, exact encoded-representation/descriptor digest, profile/rules identity and the canonical descriptor (including base64 E, declared sizes and H). Send E only through that descriptor, without a second raw copy on the wire. Use a bounded length-prefixed byte protocol rather than accepting arbitrary pickle objects or file/URL/decoder references. Cap the request at `4*ceil(B/3)+3072` bytes (descriptor parser allowance plus at most 1,024 trusted job-header bytes), and the response at A raw output bytes plus at most 1,024 status/header bytes.
2. Start with one worker and at most two waiting jobs per coordinator. Each worker handles one frame, then exits. It has no chain/database handles, signer credentials, writable application storage or network access. Scrub inherited environment/handles; expose only read-only runtime/codec files and a disposable private IPC endpoint. Every decode still uses fresh native/table/repeat state.
3. Candidate **operational**, unvalidated deployment settings are 128 MiB per process, one CPU, five CPU seconds and a five-second wall watchdog after worker readiness. These require measurement on each supported runtime/OS and are not approved defaults. Queue/memory/CPU limits may be tuned locally; exceeding them means unvalidated/defer, never an invalid block. A slow healthy node may need larger settings.
4. On Windows, create the worker suspended, apply a restricted security token/appropriate filesystem and network restrictions, assign it to a Job Object with committed-memory and CPU limits, no breakaway and kill-on-job-close, then resume. Treat inability to establish the required restrictions as local unavailability. Job resource limits do not themselves remove filesystem/network privileges. [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects), [extended limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).
5. On Linux, use a dedicated cgroup with memory, CPU-rate and process-count controls, a per-process CPU-time rlimit for the cumulative budget, read-only filesystem/network namespaces and restricted syscalls/credentials; establish controls before accepting a job. CPU-rate throttling alone does not impose a total CPU-time budget. Validate host support rather than silently running without limits. [cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html), [CPU-time resource limits](https://docs.python.org/3.13/library/resource.html).
6. Cancellation kills/reaps the entire disposable worker/job, closes its private channel and discards partial/late output. Do not reuse a process, queue, pipe or lock after forceful termination. Avoid shared mutable state and shared process-pool queues: termination can corrupt IPC or leave locks held. [Python process-termination semantics](https://docs.python.org/3.13/library/multiprocessing.html).
7. The coordinator requires the correct job/profile/representation identity, terminal success, exact output length and original hash before exposing bytes. It rechecks M's length/SHA-256 and bounds every IPC response. A verified worker result still requires the later block/evidence/context checks; sandboxing does not prove decoder correctness.
8. Represent deterministic `INVALID(stage,code)` separately from `LOCAL_UNVALIDATED` (OOM, crash, timeout, cancellation, unsupported setup, inconsistent worker result). A local failure emits no vote, persistence, import success or media body. Retry/backpressure and unhealthy-node reporting belong to local scheduling.

Required worker tests include kill before/after readiness, native crash, deliberate memory/CPU exhaustion, queue saturation, cancellation during result transfer, oversized/truncated IPC, stale/wrong job IDs, child escape attempts, no inherited credentials/state handles, unsupported enforcement setup and recovery without orphan processes. Run all golden vectors normally and verify operational failures never change their consensus classification. This design is review material, not an implemented isolation guarantee or the beginning of a subsequent task.

## Verification, independence and review disposition

The new [differential tests](../tests/test_milestone_7_task_7_6b_performance.py) compare all golden outcomes, exact error stages/codes, original bytes/counts and work counters against committed Task 7.6A. They exercise widths 0–31 at every bit alignment with byte and memoryview input, retain width/overrun rejections, mutate bounded repeat/FSE streams and compare varied histories. Existing Task 7.6/7.6A, corpus and adjacent serialization tests remain in the run; difficult maximum-match cases are retained.

Final regression result: **288 passed in 81.41 seconds** (199 existing focused/adjacent tests plus 89 new differential/resource-evidence tests). All **152 frozen vectors** retain their classification: **42 accepted, 110 rejected, zero unvalidated**. Accepted vectors retain exact bytes, consumed/produced counts and verifier work; rejected vectors retain error stages/codes. All **36 corpus samples** reconstruct byte-for-byte, with original hashes matching the prior manifest; all 46 performance-case reconstructions also match. No acceptance/rejection regression was observed.

`git diff --check` passes. Recorded source hashes match the final verifier, unchanged strict adapter and benchmark runner. New-file UTF-8, trailing whitespace, final newlines and local report links were checked. Frozen vectors/manifests, historical measurements, the adapter, security/conformance contracts, dependencies and production paths are unchanged. Final branch/HEAD match the baseline above. The worktree contains exactly one modified tracked verifier and four new files (runner, tests, measurements and this report); nothing is staged or committed.

The reference/optimized comparison is **not independent implementation verification**: both originate from this prototype and use libzstd. No independent Go/Rust/Zstd decoder was available on the checked toolchain paths, no second OS/architecture was executed, and no package was installed solely to fill that gap. Independent decoder/verifier security review remains mandatory.

Remaining blockers: independent review/fuzzing of sequence/FSE/repeat handling; full native Huffman/table/error-path work proof and portable working-state/stack accounting; independent decoder and supported-platform agreement; an audited efficient native implementation if Python throughput is insufficient; the worker controls above; and later launch-policy/block/admission/storage/sync/import/reorg integration and media-worker isolation work. No production security sign-off follows from speedups or passing differential tests.

**Task 7.6B is ready for prototype review and a later authorized commit**, including review of the host timing variability and explicitly incomplete native/independent/worker evidence. This is not production integration readiness or security approval. Nothing is committed by this task.
