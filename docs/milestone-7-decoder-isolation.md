# Milestone 7 Task 7.6C — Isolated decoder worker and resource containment

Date: 2026-10-18. Scope: offline prototype only. Windows process/resource containment is implemented and tested; Linux enforcement and protection against a compromised native decoder remain incomplete. No production security approval is claimed.

## Repository and scope

Verified branch `Compression-State-Bloat-and-Node-Economics`, HEAD `86838da59d41964d8a0714720bdbf6d44a98a239`, separately committed `Milestone 7 Task 7.6B: optimize strict decoder verification`. Initial worktree was clean. No applicable repository/ancestor `AGENTS.md` was found. Read the [security contract](milestone-7-codec-security-contract.md), [conformance report](milestone-7-decoder-conformance.md), [performance report](milestone-7-decoder-performance.md), strict decoder/verifier and focused fixtures/tests. Investigation stayed within this boundary and the OS controls required here.

The existing strict decoder, sequence verifier, frozen vectors, dependency pins, historical measurements and protocol contracts are unchanged. New files:

- [Coordinator](../codec_prototype/isolated_decoder.py): synchronous bounded worker interface and explicit outcome model.
- [Windows launcher](../codec_prototype/worker_windows.py): Job Object creation, atomic assignment, limited handle inheritance, termination/accounting/reaping.
- [Worker entry](../codec_prototype/worker_entry.py): one request and one result, using the existing decoder.
- [IPC](../codec_prototype/worker_ipc.py): bounded binary framing and canonical flat JSON metadata.
- [Fault fixture](../tests/helpers/decoder_worker_fixture.py) and [focused tests](../tests/test_milestone_7_task_7_6c_isolation.py).
- [Measurement/replay runner](../scripts/milestone_7_task_7_6c_isolation.py), [results](../benchmarks/milestone_7_task_7_6c_results.json), and this report.

No production consensus, block creation/format, admission, synchronization, API, persistence, media screening, bounty or reset path is changed. No new codec, dependency or executable supplied by a media creator is accepted. No commit, staging, push, merge, deployment or subsequent-task implementation is performed.

## Architecture and lifecycle

`IsolatedDecoder.validate(raw_canonical_descriptor_bytes, cancel=Event)` parses only the bounded canonical descriptor in the caller. It does not base64-decode E, inspect compressed sequences, load the native backend or reconstruct media. Only the new child calls `strict_decoder.decode`. Existing offline reference tests intentionally retain direct decoding of frozen controlled fixtures; this is not a production caller fallback. Tests replace the caller's decode/payload/backend functions with failures and still reconstruct through the child.

```python
from codec_prototype.isolated_decoder import IsolatedDecoder, Status

with IsolatedDecoder(max_workers=1) as decoder:
    result = decoder.validate(canonical_descriptor_bytes, cancel=cancel_event)
    if result.status == Status.VALID:
        verified_original = result.original
    # INVALID and INDETERMINATE_LOCAL_FAILURE never expose original bytes.
```

1. Acquire both the instance slot and a shared host-process slot without waiting. Busy callers receive a local saturation outcome. There is no worker queue or automatic retry.
2. Bound/parse raw descriptor JSON using the existing canonical parser. Known deterministic JSON errors return the existing stage/code before launching a worker. Recheck cancellation before dispatch.
3. Configure a fresh anonymous Windows Job Object and create the process with atomic job membership. No untrusted job bytes are sent before the worker's READY message.
4. Use the base interpreter with `-I -u`, a fixed repository worker file and the trusted virtual environment's site-packages directory. The Windows venv redirector is avoided because it creates an extra process. Neither the command nor import paths come from the descriptor. Environment inheritance is reduced to SystemRoot/WINDIR/TEMP/TMP; only stdin/stdout/NUL handles are inherited. No console window is created.
5. The child imports the fixed strict decoder, checks the pinned backend and emits READY. It reads exactly one bounded request, verifies its digest and input EOF, performs canonical parsing and strict decoding, emits one terminal result and exits.
6. One bounded exchange thread per admitted call handles potentially blocking pipes. The caller monitors startup/execution deadlines and cancellation. It accepts a result only after complete response EOF and clean process exit, then independently verifies output length/SHA-256 and request identity.
7. On failure/cancellation, terminate the whole job, wait for exit, close the job/pipes/process handle and join the exchange thread. Routine failures release capacity. Uncertain cleanup/accounting returns local failure and permanently reserves the affected capacity rather than permitting accumulating jobs. Recovery from that unhealthy host state requires operator investigation/restart; it is not an automatic retry loop.
8. Every subsequent request gets a new process, job, channels and decoder state. `close()` cancels active calls and waits up to five seconds for callers to finish cleanup; a shutdown timeout is explicit. Use the context manager. Cancelling an already-running executor Future alone does not cancel its underlying call: set the supplied Event or close the coordinator.

Parent JSON parsing is finite and covered by the in-flight gates, but is not itself under the child's CPU/memory limit. Cancellation during that bounded synchronous parse is observed before dispatch. The process-creation system call is also synchronous. A failed OS shutdown cannot be hidden behind a successful result.

## IPC contract

Every message has a 12-byte network-order prefix `magic[4] || metadata_length[u32] || body_length[u32]`. Magic is `ZCW1`; metadata is at most 1,024 bytes, canonical ASCII JSON with flat string/integer values. Duplicate keys, nested/escaped metadata, booleans, unknown result fields, unexpected versions/statuses, truncated messages and trailing response bytes fail locally. No pickle, executable names, paths, URLs, codec code or decoder options are deserialized from IPC.

| Message | Metadata | Body cap |
| --- | --- | --- |
| READY | Exactly `v=1, kind=ready` | Zero |
| Request | `v=1, kind=request`, random 128-bit job ID, SHA-256 of exact descriptor bytes | `4*ceil(B/3)+2048 = 2,798,252` bytes at B=2 MiB |
| VALID | Same version/job/request digest; status, exact output size/SHA-256, diagnostic parse/decode nanoseconds | Min(valid declared original size, A=2 MiB) |
| INVALID | Same identity; status and bounded stable decoder stage/code | Zero |
| INDETERMINATE_LOCAL_FAILURE | Same identity; status and bounded local reason | Zero |

Including prefix/maximum metadata, maximum request wire size is 2,799,288 bytes; maximum response wire size is 2,098,188 bytes. Length caps are checked before body allocation. Each body uses a bounded exact-length buffer; truncated reads cannot grow it. Writes handle partial pipe writes. The child checks request EOF; the parent checks response EOF and clean exit. Unexpected body bytes on non-VALID outcomes are discarded and treated as malformed IPC.

The descriptor carries E only once, as its existing base64 payload. M is returned as raw bytes, without another base64 encoding or JSON media copy. The parent always checks M's actual length and SHA-256 against both the descriptor and response, and verifies job/request identity. Its immutable result conversion can temporarily duplicate a bounded read buffer. Bounded metadata/body copies, parent parsing and hash work remain; this is not zero-copy IPC. Callers can retain returned results indefinitely, so application-level retention/caching budgets are outside the in-flight bound.

This is a private IPC version, not a new canonical block schema/profile. Job identity prevents accidental stale/cross-request result reuse; it does not prove a compromised worker computed the right answer. Trusted immutable runtime files and decoder correctness remain prerequisites.

## Enforced Windows controls and limitations

Tested on Windows 11 AMD64 with CPython 3.13.5, zstandard 0.25.0, libzstd 1.5.7 and CFFI 2.0.0. Enforcement failure returns local unavailability without an uncontained fallback. Atomic job assignment uses `PROC_THREAD_ATTRIBUTE_JOB_LIST` at `CreateProcessW`, supported on Windows 10 and later. [Windows process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).

| Control | Default / enforced meaning |
| --- | --- |
| Process and job committed memory | 128 MiB each, set before process creation; allocation can fail below this if host/nested-job resources are tighter |
| CPU time | Five seconds of **user-mode** process CPU: native Job Object limit plus a parent-sampled CPU watchdog; kernel time is recorded separately and not covered by this counter |
| CPU parallelism | Affinity to one allowed CPU; current implementation selects the lowest allowed bit, so simultaneous workers share that selected CPU |
| Active process count | One process in each job; ordinary child creation is blocked, and neither breakaway flag is enabled |
| Startup watchdog | Five elapsed seconds through READY |
| Execution watchdog | Ten elapsed seconds after READY, including IPC and worker exit |
| Aggregate concurrency | At most two admitted jobs across all instances **in one coordinator OS process**, default one per instance; zero queued jobs |
| Parent death | Parent owns the only job handle; kill-on-job-close terminates job members when the parent dies |
| Explicit cleanup | Job termination, two-second process wait, channel closure and two-second exchange-thread join; incomplete cleanup quarantines capacity |

Memory is committed virtual memory, not a hard physical-RSS limit. Supported local configuration is 16–256 MiB memory, 0.1–30 user CPU seconds, 0.1–60 execution seconds and 0.1–15 startup seconds, with finite strict types. At maximum configuration, two workers can reserve up to 512 MiB of job commit, excluding the coordinator and host/kernel costs. Separate coordinator OS processes have separate slot budgets; deployment must bound their count. These are operational settings, not consensus constants or recommended production defaults. [Windows memory limit/accounting fields](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information), [basic CPU/process limits](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_limit_information).

An initial controlled spin exposed delayed native CPU enforcement: with a configured 0.2-second user CPU limit, the three-second wall watchdog killed the process after 2.922 user CPU seconds. Windows documents periodic CPU-limit checks. The final implementation therefore samples [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes) in the monitor loop and kills the job once observed user CPU reaches its budget, alongside the native limit. Both watchdogs can overshoot under scheduling/OS delays; neither is an exact instruction/time ceiling or consensus test. The final CPU fault measurements below reflect this added guard, rather than treating configured limit readback as evidence of timely termination.

The job is anonymous and its handle is not inherited. Atomic assignment removes a create-then-assign orphan interval. The parent-death test kills an actual separate coordinator and observes the exact child process handle become signalled. [Job lifetime/termination semantics](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

**This is not a strong security sandbox.** No restricted token, AppContainer, filesystem/network denial, syscall filtering or privilege separation is implemented. The worker remains under the caller's user identity. Native code execution could access that user's files, network, credentials/services or other same-user processes, including attempts to duplicate handles or launch indirectly through services. The active-process test covers ordinary direct process creation, not every privilege-based escape. Python isolated import mode and reduced environment/handle inheritance do not remove those OS privileges. Threads, native stack/kernel allocations, native error-path work and all indirect process mechanisms are not exhaustively audited. The launch lock serializes this module's inheritance window; unrelated host code performing broad handle inheritance would require deployment review. These are production blockers, not claimed guarantees.

## Linux and other platforms

Linux enforcement is **not implemented or tested**. A canonical request on an unsupported platform returns `INDETERMINATE_LOCAL_FAILURE(unsupported_platform)` without dispatching or decoding in the parent. Cheap deterministic JSON errors can still return INVALID before platform dispatch. A Python platform launcher or an installed subsystem does not constitute Linux execution evidence.

A separate Linux implementation needs controls established before untrusted work, a constrained process/identity, cgroup memory/process/CPU-rate limits, cumulative CPU-time limits, restricted filesystem/network/syscalls, bounded inherited descriptors and reliable parent-death/whole-tree cleanup. CPU rate alone is not a cumulative execution budget. cgroup access/support failures must be local failures; no permissive subprocess fallback is acceptable. Test native crashes, parent death, cancellation, group cleanup, privilege removal and all vectors on the real supported kernel/runtime. [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html), [Unix resource limits](https://docs.python.org/3.13/library/resource.html).

## Consensus outcomes, retry and peer behavior

| Outcome | Meaning | Permitted next behavior |
| --- | --- | --- |
| VALID | Existing strict profile passed; verified exact M is available | Later context/media/block/evidence checks still required; this alone does not accept a block |
| INVALID | A deterministic existing descriptor/frame/output/hash/work restriction failed | Preserve stable stage/code; no new validity rule or elapsed-time predicate is introduced |
| INDETERMINATE_LOCAL_FAILURE | Saturation, startup/control failure, unsupported OS, OOM, timeout, crash, cancellation, malformed IPC/result or unproven cleanup | Discard partial/late bytes; defer/backpressure/retry explicitly under a bounded caller policy; no vote, accepted import, persistence or media success |

Zstd data that is otherwise decodable but exceeds the frozen profile's block/output/sequence restrictions is INVALID under that profile. A valid maximum-match frame killed by a shorter operational budget is **indeterminate**, not INVALID. CPU-limit termination is local even if Windows reports a resource-limit exit code; an IPC EOF/crash is never inferred to prove malformed media. A worker-reported local failure also remains indeterminate.

The prototype performs no automatic retries or peer actions. A future caller must bound attempts/backoff, avoid recursion/retry storms and avoid penalizing/banning a peer or discarding an otherwise undecided block solely for local saturation/time/resource failure. A healthy fresh request can validate the same bytes that previously timed out. Cleanup uncertainty makes the host unhealthy and reserves capacity until investigation/restart. Local operator budgets may differ across nodes without altering deterministic validity. Raw native error text is not serialized as a protocol error.

## Adversarial verification

Focused tests cover every requested category:

- Small/large valid images, high-ratio full-A data, all golden vectors and all corpus samples; original hashes/bytes and stable error stages/codes agree.
- Bad descriptors/JSON, malformed/truncated frames, excessive decoded output, sequence-count/output inconsistency, full 699,050 matches and actual-offset/window violations, via unchanged frozen vectors and existing decoder regressions.
- Prefix/body oversize rejection before body reads, malformed/duplicate/nested metadata, partial writes, unexpected statuses/fields, wrong job/request identity, wrong output hash/size, extra/truncated output, nonzero exit after a reply and response EOF followed by a hanging process.
- Controlled startup hang, execution hang, crash, external termination, pre-cancellation, active cancellation, coordinator close, repeated failure with fresh recovery and no automatic retry, shared concurrency saturation and capacity recovery.
- Actual 32 MiB job allocation denial for a bounded 64 MiB request, direct child-creation denial, and a controlled CPU spin stopped by the sampled CPU guard/native budget before the longer wall deadline. These avoid unbounded exhaustion.
- Real parent death kills its worker; repeated requests release parent native handles; exchange threads do not accumulate. Simulated accounting failure after real process reaping returns local failure and quarantines capacity.

Final regression: **492 passed in 59.77 seconds**, including all 288 prior focused/adjacent tests and 204 worker/IPC/resource-evidence tests. There were no skipped tests on this Windows host. The earlier focused worker run passed 203 tests before the final evidence test/CPU guard changes; nine targeted CPU/memory/cancellation/cleanup checks then passed, and the full final suite covers the final code and artifact.

The final measurement runner independently replays **152 frozen vectors through workers: 42 VALID, 110 INVALID, zero indeterminate**, with identical expected stages/codes and exact accepted original bytes. All **36 corpus samples** reconstruct exactly and match the previous manifest. All seven performance cases reconstruct exactly. Fault-injection outcomes are intentionally indeterminate and all measured processes are reaped. This is replay of the same implementation, not independent algorithm validation.

## Performance, memory and worker lifetime

The [runner/results](../benchmarks/milestone_7_task_7_6c_results.json) record source hashes, exact input hashes, toolchain, raw timings, OS counters and every replay outcome. Three independent per-request workers follow one complete warmup job per measured input. p95 is nearest rank and equals worst with three samples; it is not a population-tail guarantee. No speed thresholds affect validation or test classification.

The caller never performs an in-process media baseline decode. `worker_decode_ns` measures the unchanged strict `decode(dict)` inside the job; worker canonical JSON parsing is measured separately. End-to-end latency additionally includes caller canonical parsing, OS startup/backend import, pipe transport, parent output authentication, exit and cleanup. `exchange minus worker parse/decode` is an IPC/allocation/exit/scheduling estimate, not a pure transport benchmark. The historical Task 7.6B artifact is retained/hash-bound for comparison; its substantial host runtime shifts mean it is not a paired stationary baseline for these fresh single-job processes.

Final measured values follow. Times are milliseconds; each end-to-end cell is **median / p95 / worst**. The other columns are medians, except peak job commit, which is the largest observed value in MiB. Every row reconstructs exact original bytes. Samples come from fresh per-request workers with the final CPU watchdog enabled.

| Input | End-to-end ms | Startup ms | Worker decode ms | Child JSON ms | Cleanup ms | Peak job commit MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Small flat JPEG | 125.983 / 140.991 / 140.991 | 105.174 | 0.293 | 0.088 | 0.110 | 12.527 |
| Medium mixed JPEG | 125.718 / 140.419 / 140.419 | 101.369 | 0.952 | 0.492 | 0.119 | 12.699 |
| High-entropy capacity PNG | 314.232 / 329.381 / 329.381 | 111.082 | 9.569 | 83.700 | 0.110 | 23.137 |
| Highly compressed 2 MiB | 138.644 / 139.996 / 139.996 | 105.718 | 1.937 | 0.033 | 0.118 | 16.660 |
| Identity at 2 MiB | 341.322 / 341.680 / 341.680 | 118.873 | 10.418 | 86.260 | 0.114 | 25.133 |
| 699,050 short matches | 641.398 / 642.964 / 642.964 | 109.156 | 487.954 | 7.099 | 0.105 | 17.410 |
| 64 blocks rebuilding maximum tables | 155.491 / 157.376 / 157.376 | 110.417 | 16.749 | 0.088 | 0.190 | 12.578 |

Parent JSON preflight and reauthentication/monitor scheduling are additional end-to-end costs; stage medians cannot simply be summed. In particular, large base64 descriptors incur two canonical JSON passes, one in the parent and one in the disposable child. Avoiding these checks only for benchmark speed is not part of this change.

Median IPC/exit/allocation/scheduling estimates (`exchange minus worker JSON/decode`) range **6.072–12.071 ms**, with **9.256 ms** for maximum matches. These exclude caller canonical parsing/response hash work outside the exchange interval. Normal median cleanup is **0.105–0.190 ms**; the controlled crash, hang and CPU-stop cleanup samples are **1.013, 3.507 and 1.838 ms**, respectively.

The historical Task 7.6B in-process after medians were 0.084 ms for small JPEG, 4.089 ms for medium JPEG, 52.418 ms for capacity PNG and 3,309.205 ms for maximum matches. That task also observed a fresh maximum-match decode at 473 ms. Here the unchanged decoder's fresh child median is 487.954 ms and the whole isolated request is 641.398 ms. This supports a local startup/transport overhead comparison; cross-artifact ratios cannot establish that isolation accelerated decoding, given the earlier runtime variation and fresh-process versus repeated-call conditions. The total isolated path additionally validates raw canonical JSON, whereas the historical total began at `decode(dict)`.

Three finite batches of eight small JPEG jobs each measured **7.682, 8.037, 7.886 jobs/s** at concurrency one and **10.422, 10.306, 10.250 jobs/s** at concurrency two. These are startup-dominated synthetic jobs with at most two active workers. Both jobs use the selected allowed CPU; results do not establish network throughput or a worst-case service rate. No saturation retry is hidden in the measurements.

Across the measured latency cases, peak job commit is at most **25.133 MiB**, against a 128 MiB configured cap. Parent-only traced peaks are **9,792,200 bytes** for full-A identity and **4,459,561 bytes** for maximum matches. After the last main measurement, parent process high-water values are **82,026,496 working-set bytes** and **72,626,176 committed bytes**, including harness state, retained corpus and result objects. They are observations, not per-request overhead bounds or limits imposed on the parent.

Controlled resource evidence with 32 MiB/0.2-user-second jobs:

| Fault | Final outcome/reason | Evidence |
| --- | --- | --- |
| Abrupt exit | INDETERMINATE_LOCAL_FAILURE / `worker_crash_or_ipc` | Exit 23; reaped |
| Hang | INDETERMINATE_LOCAL_FAILURE / `timeout` | Job killed (exit 71); reaped |
| CPU spin | INDETERMINATE_LOCAL_FAILURE / `cpu_limit` | Sampled guard stopped at 203.125 ms user CPU; job killed/reaped before three-second wall budget |
| Bounded 64 MiB allocation attempt | INDETERMINATE_LOCAL_FAILURE / `worker_memory_limit_confirmed` | Allocation denied under the 32 MiB limit; clean worker exit/reap |
| Direct child creation attempt | INDETERMINATE_LOCAL_FAILURE / `worker_child_limit_confirmed` | Active-process limit prevented the new process; clean worker exit/reap |

These fault measurements are single observations, not distributions. No partial original bytes are returned. The stronger final CPU guard was added because the earlier native-limit-only experiment failed to stop the short-budget spin promptly; that finding is retained above.

Windows peak process/job commit comes from OS Job Object counters, including native/interpreter memory; it is not a Python-only estimate or physical RSS. Parent working set/commit comes from [GetProcessMemoryInfo](https://learn.microsoft.com/en-us/windows/win32/api/psapi/nf-psapi-getprocessmemoryinfo); process peaks are cumulative and include the measurement harness's retained corpus/results. Parent-only allocation tracing runs after latency measurements; it excludes caller-owned inputs already held, native/kernel allocations and the child. It is not a portable parent-memory ceiling. The interface bounds in-flight allocations; it cannot bound unrelated allocations or caller-retained results.

Per-request workers are preferred for this prototype: fresh process/native state, disposable private pipes and an empty job for every operation simplify failure cleanup and eliminate cross-request worker contamination. Startup dominates tiny inputs. Persistent workers might improve throughput, but require separate lifecycle, memory-growth, recycling, state-reset and cancellation review; none are implemented simply to improve benchmark scores.

## Remaining blockers and disposition

Independent decoder/verifier review is still absent: another process runs the same Python verifier and libzstd, not an independent algorithm. Frozen agreement and process/resource isolation do not establish native correctness or resistance to arbitrary native execution. Remaining production blockers include Windows privilege/filesystem/network confinement; implemented/tested Linux controls and supported architectures; independent parsing/sequence/FSE/Huffman review, fuzzing/sanitizers and native state/stack/error-path accounting; real-host resource/latency repeatability; immutable deployment/runtime/handle policy; and separate launch-policy/block/admission/sync/API/storage/media integration and validation. The existing independent media-screening isolation issue is not fixed by this codec prototype.

**Task 7.6C is ready for review and a later authorized prototype commit**, with Windows resource containment implemented and Linux/strong-sandbox gaps explicitly retained. Final branch/HEAD remain the verified values above. All recorded source hashes match the final files. Final worktree scope is nine new files listed above; existing tracked files and historical measurements remain unchanged, and nothing is staged or committed. Whitespace/UTF-8/newline/link checks and `git diff --check` pass. Production integration remains blocked; no production security approval or next-task implementation is implied.

## Reproduction commands

Run from the repository root using the existing environment. Long output is saved to ignored `temp/` logs.

```powershell
# Focused real-worker suite (also exercises all vectors/corpus):
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_6c_isolation.py -q --tb=short > temp/task76c-worker-tests.txt 2>&1

# Final measurements/replay, with no concurrent test workload:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6c_isolation.py > temp/task76c-measurements.txt 2>&1

# Full focused + adjacent regression suite:
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py tests/test_milestone_7_task_7_6b_performance.py tests/test_milestone_7_task_7_6c_isolation.py tests/test_milestone_7_task_7_3_corpus.py tests/test_milestone_7_task_7_4_benchmark.py tests/test_milestone_7_task_7_4a_image_evaluation.py tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime -q --tb=short > temp/task76c-regression.txt 2>&1
git diff --check
```
