# Milestone 7 Task 7.6D — Linux decoder worker isolation

Date: 2026-10-18 (America/New_York). Offline prototype only. **Implementation is ready for review; production security approval remains blocked.** Actual Linux process tests ran as UID 1000 on Ubuntu 24.04.2 LTS under WSL2, x86_64, kernel `6.6.87.2-microsoft-standard-WSL2`, CPython 3.12.3. These are Linux kernel execution results, not native Ubuntu deployment or architecture coverage. Windows compatibility was also exercised on the existing Windows host, CPython 3.13.5. Both use zstandard 0.25.0, libzstd 1.5.7 and CFFI 2.0.0.

## Repository, scope and files

Expected/actual branch: `Compression-State-Bloat-and-Node-Economics`. Starting and final HEAD: `8607636cc13d1c78c73de3da09fa8d149f8af0f0`, separately committed Task 7.6C (`Milestone 7 Task 7.6C: isolate decoder with Windows worker containment`). Initial worktree clean. No applicable repository/ancestor or relevant-subdirectory `AGENTS.md` was found. Read the requested conformance, performance, isolation and codec-security reports; exploration stayed within the codec, worker, fixtures and supporting corpus/test tools.

Modified:

- [Coordinator](../codec_prototype/isolated_decoder.py): platform dispatch and bounded startup-unavailability diagnostics.
- [Shared worker](../codec_prototype/worker_entry.py): trusted pre-READY confinement hook; decoding and response semantics unchanged.
- [7.6C tests](../tests/test_milestone_7_task_7_6c_isolation.py): unsupported-platform fixture and historical artifact hashes, now checked against the committed 7.6C sources instead of later platform additions.
- [Existing isolation report](milestone-7-decoder-isolation.md): historical context and link to this report.

Created:

- [Linux launcher/controls](../codec_prototype/worker_linux.py) and [Linux bootstrap](../codec_prototype/worker_linux_entry.py).
- [Safe Linux fault fixture](../tests/helpers/linux_decoder_worker_fixture.py), [Linux tests](../tests/test_milestone_7_task_7_6d_linux_isolation.py), and [paired-evidence test](../tests/test_milestone_7_task_7_6d_evidence.py).
- [Replay/measurement runner](../scripts/milestone_7_task_7_6d_isolation.py), [Linux evidence](../benchmarks/milestone_7_task_7_6d_linux_results.json), [Windows evidence](../benchmarks/milestone_7_task_7_6d_windows_results.json), and this report.

Final worktree: four modified and nine new task files, unstaged. No production modules, decoder/sequence grammar, fixtures/manifests, dependency specifications, historical measurements, block format, chain state or deployment configuration changed. No commit, push, merge, deployment, reset, bounty or subsequent task work occurred. Test packages and the portable input bundle reside only in ignored `temp/`.

## Architecture and outcomes

The existing coordinator admits at most two requests across all instances in one coordinator process, with no waiting queue and no automatic retries. Each request starts a fresh interpreter in isolated mode with private stdin/stdout pipes, stderr directed to the null device, closed ambient descriptors, a minimal environment, and a new session/process group. The Linux launcher uses `Popen(start_new_session=True, close_fds=True)`, with no Python `preexec_fn` in the threaded coordinator.

The trusted bootstrap arms `PR_SET_PDEATHSIG(SIGKILL)`, checks the expected parent PID and creating thread's existence, refuses root or mismatched real/effective identities, drops and verifies capability sets, disables dumpability, sets/verifies `no_new_privs`, and installs/readbacks hard resource limits. It loads the existing pinned backend, closes descriptors above 2 and requires a single-threaded bootstrap. It then loads a mandatory libseccomp filter before sending READY. Only after READY does the coordinator send descriptor bytes. The strict decoder, sequence verifier, hash/consumption checks and original-byte result are shared with Windows.

Existing IPC bounds remain: `MAX_REQUEST=2,798,252` bytes, at most 1,024 bytes of flat canonical metadata, at most the declared original size (and at most 2 MiB) of raw response bytes. Lengths are checked before allocations; no pickle, object graph, URL, creator executable or codec registry is accepted. The parent only parses bounded canonical descriptor JSON, then authenticates returned size/hash/request identity and requires clean process exit. It never reconstructs media itself.

`VALID` and `INVALID(stage,code)` preserve the frozen protocol profile. `INDETERMINATE_LOCAL_FAILURE` covers OS/resource/startup/CPU/wall failures, saturation, cancellation, crash, malformed IPC and cleanup uncertainty. Missing mandatory controls emit bounded specific startup reasons such as `linux_seccomp_unavailable`, `linux_resource_controls_unavailable`, `linux_privileged_identity`, `linux_no_new_privs_unavailable`, or `linux_backend_unavailable`. No unrestricted fallback or retry occurs. Cheap deterministic descriptor-transport rejection can still precede platform dispatch. Parent disappearance during trusted startup exits without reading a request. Native CPU termination may be diagnosed as crash/IPC loss; it still never becomes INVALID.

The existing wall watchdog covers five seconds through READY and ten seconds after READY, including IPC and exit. Cancellation/timeout kills the process group while its leader PID remains owned/unreaped, then waits/reaps and closes channels. The adapter serializes reap and group signals, avoiding post-reap signals to recycled group IDs. After confinement no fork/clone/exec or group/session changes are permitted, so untrusted work cannot create descendants or escape the group. Cleanup/accounting/thread-join uncertainty reserves the slot until host investigation/restart, preventing accumulation through capacity reuse.

## Controls actually enforced

| Requirement | Linux launcher/worker enforcement | Boundary/qualification |
| --- | --- | --- |
| Fresh process | New interpreter and session/group per request | Trusted runtime imports precede confinement; no media is read then |
| Address space/native memory | Hard/soft `RLIMIT_AS`, default 128 MiB; inherited tighter hard limits retained | Covers interpreter/native mappings after setup; not a physical RSS or cgroup aggregate limit |
| CPU budget | Hard/soft `RLIMIT_CPU=ceil(cpu_seconds)`, default 5 seconds; parent samples `/proc/PID/stat` user + system CPU for fractional budgets | Kernel hard limit is integer seconds; scheduling and sampling can overshoot; includes startup CPU |
| CPU parallelism | Affinity restricted to one already-allowed CPU | Lowest allowed CPU chosen, so simultaneous workers normally share that CPU |
| Wall time | Shared startup/execution watchdogs | Operational failure only; no consensus time predicate |
| Processes/threads | `RLIMIT_NPROC=1` plus seccomp denial of fork/vfork/clone/clone3/execve/execveat | NPROC counts tasks for real UID, not a per-job cgroup; seccomp is the primary creation prohibition |
| File descriptors | Close inherited FDs; close any bootstrap-opened FD above 2; hard/soft NOFILE=16 | Only request pipe, result pipe and null stderr remain; no descriptor duplication/acquisition calls allowed |
| Filesystem | Default-deny seccomp excludes open/openat/openat2, directory, mutation and mount operations | No path opens after READY, including signing keys and databases; not a filesystem namespace |
| Network | No socket/socketpair/connect/accept/send/receive or io_uring calls; no inherited network FDs | IPv4, IPv6 and Unix socket creation probes denied; no network namespace claimed |
| Privileges | Non-root equal real/effective IDs; empty effective/permitted/inheritable capabilities; irreversible `no_new_privs`; no credential/capability/namespace/exec syscalls | Same UID and supplementary groups retained; no dedicated worker identity or LSM policy |
| Other processes | No ptrace/process_vm/pidfd descriptor acquisition, kill/tgkill or process-management syscalls | Does not isolate the parent from hostile host processes outside this worker |
| Parent death | SIGKILL on death of creating parent thread; expected parent PID/TID checked after arming | Applies once bootstrap runs; a kernel/runtime stall before bootstrap is not an atomic launch-time guarantee |
| Core/files/locked pages | CORE=0, FSIZE=0, MEMLOCK=0 hard/soft limits; dumpable=0 | Not comprehensive control of all kernel memory/accounting |
| Capacity/retry | Two global slots per coordinator process; default one per instance; zero queued/retried jobs | Operator must bound number of coordinators and upstream retained work/results |

The syscall policy is an allowlist, not a list of known dangerous calls. Default native-ABI action is EPERM; foreign/unconfigured ABI calls are rejected by libseccomp. Allowed calls are memory allocation/protection/advice, signal handlers/masks/return, futex, clocks/sleep/restart, PID/TID queries, randomness, scheduler yield, resource accounting, fstat, close and exit. `read` is allowed only on fd 0; `write` only on fd 1 or 2. No filter-removal, limit-raising, process-creation, arbitrary filesystem, network or privilege operations are allowed. The exact named list is retained in `worker_linux.ALLOWED_SYSCALLS`; unsupported names/library/filter installation fail closed. Bootstrap threads are refused, preventing a thread outside the installed filter.

These controls reduce exposed authority and kernel surface; they do not prove complete sandbox security. Resource limits alone are insufficient. See [Linux seccomp documentation](https://kernel.org/doc/html/latest/userspace-api/seccomp_filter.html), [resource-limit semantics](https://man7.org/linux/man-pages/man2/getrlimit.2.html), [no_new_privs limitations](https://cdn.kernel.org/doc/html/latest/userspace-api/no_new_privs.html), and [parent-thread/death-race semantics](https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html).

## Missing controls, operator prerequisites and Ubuntu compatibility

No cgroups, user/mount/network/PID namespaces, Landlock/AppArmor policy, chroot, separate worker UID, syscall-argument audit for every allowed memory operation, or executable-memory prohibition are implemented. The worker cannot open keys/database paths after confinement, but the trusted Python startup/backend/import phase runs with the caller's filesystem identity. Trusted code/runtime/site-packages must be immutable, must not load keys or application state, and must not spawn background processes. Python isolated mode still trusts installed runtime/site initialization. Existing same-user hostile processes, malicious runtime code, a compromised parent, or a kernel vulnerability are outside the demonstrated confinement boundary. No defense against arbitrary native-code exploitation of the remaining permitted kernel interface is claimed.

The bootstrap checks parent PID/TID after arming PDEATHSIG, closing the ordinary death-before-arm race once scheduled. It cannot guarantee cleanup while the interpreter is indefinitely stalled before reaching bootstrap. There is no atomic cgroup assignment before exec, host-wide OOM containment, memory-bandwidth/I/O quota, physical RSS cap, aggregate process limit across coordinators, or launch-time CPU-rate throttle. CPU affinity and cumulative time are not cgroup CPU-rate control. A service manager or supervisor must reap orphans after coordinator death; the test harness explicitly adopts/reaps its test orphan.

Ordinary worker operation needs no root, sudo, daemon control or cgroup delegation. Tested prerequisites are glibc x86_64 Linux, working `/proc` visibility, resource/affinity/prctl support, `libseccomp.so.2`, kernel seccomp filtering, and the pinned Python decoder dependencies. Root/set-ID launches and non-x86_64 architectures fail closed. Ubuntu 24.04 under WSL2 passed; native Ubuntu, Ubuntu 22.04, ARM64, different Python/glibc/kernel builds and stricter outer sandboxes remain unverified. Tighter inherited limits or an outer service syscall policy can cause local unavailability.

Before production review, the operator must provision a dedicated nonprivileged node/service identity with protected signing keys and databases, immutable worker runtime, bounded coordinator count/input queues, and independently reviewed service/cgroup restrictions. Evaluate delegated cgroup v2 memory/pids/CPU accounting and limits, service-wide kill/reaping on coordinator death, read-only/minimal mounts, private network/namespace or LSM restrictions, and native Ubuntu resource tests. Such provisioning is separate from ordinary rootless node operation. Existing systemd restrictions can add defense, but none were assumed active or changed here. No production unit/configuration was modified. [cgroup v2 semantics](https://docs.kernel.org/admin-guide/cgroup-v2.html).

## Test evidence and cross-platform compatibility

Final Linux worker + strict-decoder/sequence + paired-evidence regression: **376 passed in 44.31 seconds**, comprising 193 Linux worker tests, 182 existing decoder/sequence tests and the paired-evidence test. Final Windows focused/adjacent regression: **493 passed, 193 Linux-only tests skipped in 61.59 seconds**, including all 204 existing real Windows worker/IPC tests. The explicit Linux-only skips are executed in the Linux run, not counted as Linux verification on Windows. An earlier Linux-only run passed 191 tests before two additional lifecycle/quarantine checks; final results above supersede that intermediate count. No failing tests remain in these final commands.

Linux coverage includes valid small/large/high-expansion and maximum-match streams, invalid descriptors, all frozen vectors, crashes, startup/execution hangs, sampled fractional CPU budget and kernel CPU kill without the parent sampler, bounded Python allocation and native mmap denial, explicit termination/cancel/close, parent SIGKILL and adopted-child reap, parent PID/TID race rejection, group/session/affinity/limits/capability/no_new_privs/seccomp readback before sending any request, global saturation, repeated recovery without retry/reuse, FD closure, memory-limit sealing, malformed/oversized/truncated/wrong-identity/extra-output IPC, and quarantine after simulated accounting failure. Safe probes attempt to open an existing nonsensitive document, create IPv4/IPv6/Unix sockets, fork/exec a harmless command, perform a same-UID credential call and re-enable dumpability. No keys, databases, external network connections, destructive operations or actual privilege escalation were attempted. A controlled missing-libseccomp loader failure proves specific local failure with no dispatch fallback.

Each platform's final measurement runner separately replayed **152 frozen vectors: 42 VALID, 110 INVALID, zero indeterminate**, preserving stage/code and exact accepted original bytes. It also reconstructed **36/36 manifest-bound originals as Zstd and 36/36 as identity (72 streams)**. Paired evidence verifies identical canonical-request hashes for all corpus and performance cases and identical golden statuses/stages/codes. These are cross-platform results from the same strict decoder/libzstd, **not independent decoder verification**.

The first Linux corpus-generation attempt differed at `png-flat-small`: reference hash `661c37d971f8727953face7d0b8da6663ce8a1985c7ea9fab8c14aa079280632`, Linux-generated hash `7d2e93a9131fa53bd6559bdf92f5230c92e5a754824b317bf4983e548947a046`, despite matching Pillow version. Platform-native encoder output is not the decoder interoperability contract. The final runs replayed a portable bundle exported from the reference Windows environment, checking original hashes against the unchanged manifest and using the exact same canonical descriptors on both OSes. No Linux-regenerated bytes or rewritten expectations were substituted. The portable bundle's digest is recorded in both result artifacts; its 31,428,286 bytes are not committed. Encoder/corpus-generator portability remains a distinct limitation.

Historical Task 7.6C evidence remains byte-for-byte intact. Its source-hash test now reads the original committed sources, while the new paired-evidence test binds current sources, input identity and results. No measurements were relabeled as Linux evidence.

## Performance and resource measurements

All times below are milliseconds; RSS is MiB. p95 equals worst at three samples.

| Input | Linux elapsed median / p95 | Windows elapsed median / p95 | Linux startup median | Linux strict decode median | Linux total CPU median | Linux lifetime RSS peak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| jpeg-flat-small | 148.554 / 196.796 | 125.498 / 139.731 | 131.553 | 1.536 | 43.373 | 94.754 |
| jpeg-mixed-medium | 250.635 / 270.635 | 126.798 / 139.567 | 229.579 | 1.535 | 42.391 | 94.941 |
| png-noise-capacity | 212.612 / 214.240 | 314.319 / 325.925 | 90.966 | 6.945 | 96.336 | 100.004 |
| high-ratio-at-A | 109.092 / 112.738 | 122.363 / 123.724 | 86.114 | 3.283 | 44.270 | 107.504 |
| identity-at-A | 198.431 / 248.613 | 327.502 / 330.464 | 90.867 | 6.081 | 89.240 | 109.379 |
| short-matches-at-frame-A | 439.832 / 449.058 | 625.217 / 625.628 | 89.656 | 324.550 | 364.760 | 109.379 |
| 64-rebuilt-max-fse | 116.661 / 117.218 | 139.513 / 141.773 | 87.517 | 13.940 | 53.160 | 109.379 |

Normal Linux median cleanup ranged 0.016–0.026 ms; all measured requests/faults were reaped. Fresh Windows maximum job commit across the seven cases was 25.227 MiB. No child result was returned from a fault probe.

Linux finite eight-job batches measured concurrency 1: 9.745, 9.602, 9.237 jobs/s (median 9.602); concurrency 2: 16.612, 13.195, 16.939 jobs/s (median 16.612). These are startup-dominated small JPEG batches, not adversarial sustained service rates.

The 0.2-second sampled CPU probe stopped at 214.433 ms of measured user+system CPU, before its three-second wall deadline, with exit -9 and local reason `cpu_limit`. The separate sampler-free test confirms the rounded one-second kernel hard limit. Python 64 MiB allocation and native 96 MiB mmap probes failed under a 48 MiB AS cap; all confinement probes reported the expected local outcomes. Missing libseccomp was injected safely in the loader and produced `linux_seccomp_unavailable`.

Three fresh workers follow one complete warmup per measured input. End-to-end time includes parent parsing, process creation, trusted imports/confinement, IPC, strict decoding, parent authentication, exit and cleanup. p95 is nearest rank and equals the worst of three; no population-tail or worst-case performance guarantee is inferred. The final measurements ran separately without concurrent regression workloads. WSL2 filesystem/interpreter/kernel differences and shared hardware prevent a clean OS-only comparison with Windows. Historical 7.6C small JPEG/adversarial medians were 125.983/641.398 ms; the fresh Windows artifact is the more relevant current comparison.

`wait4` records per-child user/system CPU and whole-lifetime peak RSS, including native/interpreter and pre-exec fork accounting. Its high-water mark is not an isolated decoder allocator peak, newly committed physical memory, or directly comparable to Windows Job Object commit. The large retained harness/reference bundle can affect the fork-time peak. Resource metrics survive exec; see [getrusage](https://man7.org/linux/man-pages/man2/getrusage.2.html). No exact post-confinement native allocator/RSS peak, kernel memory ceiling or cgroup peak was measured. The native allocation-denial probe separately establishes RLIMIT_AS enforcement. Configured AS=128 MiB is a virtual address-space ceiling after setup; a worker inherited from a larger coordinator can have a larger lifetime peak recorded before setup. Metrics distinguish configured ceilings from actual readbacks in the kernel-state test.

At 100, 1,000 and 10,000 blocks/day, the average rate is 0.00116, 0.0116 and 0.116 validations/s **assuming one validation per block**. The following arithmetic scales measured per-request elapsed/CPU observations; it excludes all consensus, media screening, networking, disk, peer duplication, retries and bursts. It is not a capacity guarantee.

| Blocks/day | Mean validations/s | Small JPEG elapsed seconds/day | Maximum-match elapsed seconds/day | Maximum-match CPU seconds/day |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 0.00116 | 14.86 | 43.98 | 36.48 |
| 1,000 | 0.01157 | 148.55 | 439.83 | 364.76 |
| 10,000 | 0.11574 | 1485.54 | 4398.32 | 3647.60 |

The measured startup/throughput observations support retaining one disposable process per request for this prototype at those average rates. A stream consuming the full default five CPU seconds on every request would consume 13.89 CPU hours/day at 10,000 requests, before startup/other node work; adversarial bursts can saturate the two-slot limit. Operators need native-host headroom/backpressure measurements. No persistent pool is introduced; its cross-request state and cancellation risks are not justified by these limited measurements.

## Exact reproduction commands

The actual test environment was prepared without system package changes. Windows pip downloaded Linux wheels into the ignored, unbootstrapped venv site directory because Ubuntu's system Python lacked ensurepip. This is test preparation only:

```powershell
wsl.exe -d Ubuntu --exec python3 -m venv /mnt/c/Users/mattk/ZoidbergChain/temp/task76d-venv
# The preceding command created pyvenv.cfg/bin/python but reported missing ensurepip.
# Populate only that test environment; do not install into system Python:
.\.venv\Scripts\python.exe -m pip install --target temp/task76d-venv/lib/python3.12/site-packages --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp --only-binary=:all: zstandard==0.25.0 cffi==2.0.0 Pillow==12.3.0 pytest==8.4.1 Brotli==1.2.0

# Export the existing manifest-matching originals AND exact request descriptors:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6d_isolation.py --export-inputs temp/task76d-inputs.json

# Run separately from Linux measurements:
.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6d_isolation.py --inputs temp/task76d-inputs.json --output benchmarks/milestone_7_task_7_6d_windows_results.json > temp/task76d-windows-measurements.txt 2>&1
```

On Ubuntu/WSL2, from the same checkout (a normal operator-created venv with these dependencies also works):

```sh
cd /mnt/c/Users/mattk/ZoidbergChain
ZOIDBERG_TASK76D_INPUTS=temp/task76d-inputs.json temp/task76d-venv/bin/python -m pytest tests/test_milestone_7_task_7_6d_linux_isolation.py tests/test_milestone_7_task_7_6d_evidence.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py -q --tb=short > temp/task76d-linux-regression.txt 2>&1
temp/task76d-venv/bin/python scripts/milestone_7_task_7_6d_isolation.py --inputs temp/task76d-inputs.json --output benchmarks/milestone_7_task_7_6d_linux_results.json > temp/task76d-linux-measurements.txt 2>&1
```

The paired-evidence test requires both final artifacts; first generate both measurements, then run regressions. Exporting inputs requires the reference image-encoder environment; the test-only `ZOIDBERG_TASK76D_INPUTS` variable chooses the replay bundle and is not forwarded to worker environments. Without it the harness attempts reference corpus generation and refuses mismatched hashes. Frozen vectors need no producer encoder or bundle.

Final Windows focused/adjacent regression command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py tests/test_milestone_7_task_7_6b_performance.py tests/test_milestone_7_task_7_6c_isolation.py tests/test_milestone_7_task_7_6d_linux_isolation.py tests/test_milestone_7_task_7_6d_evidence.py tests/test_milestone_7_task_7_3_corpus.py tests/test_milestone_7_task_7_4_benchmark.py tests/test_milestone_7_task_7_4a_image_evaluation.py tests/test_protocol_v1.py::test_bytes_are_deterministic_and_round_trip tests/test_protocol_v1.py::test_domain_separation_changes_bytes_and_hashes tests/test_protocol_v1_golden_vectors.py::test_canonical_serialization_vectors_match_runtime tests/test_protocol_v1_golden_vectors.py::test_block_vectors_match_runtime -q --tb=short > temp/task76d-windows-regression.txt 2>&1
git diff --check
```

The broader corpus-generation/encoder benchmark tests are exercised on their reference Windows environment; native Linux regression is targeted to portable frozen vectors, exact-input worker replay and decoder/sequence behavior. No claim that the entire reference producer suite is portable is made.

## Remaining approval gates and disposition

Independent security review of the launcher, ABI/filter policy, lifetime races, permitted syscall surface and pinned runtime is still required. Native Ubuntu/architecture/deployment verification, service/cgroup/identity/filesystem defense, trusted pre-bootstrap cleanup guarantees, physical/aggregate memory accounting, independent full-decoder agreement, sequence/FSE/Huffman fuzzing/sanitizers and native error-path/state/stack/work accounting remain production gates. Windows still lacks filesystem/network/privilege confinement. The separate media-screening isolation issue is unchanged. Production consensus/admission/storage/sync/API integration and policy activation remain outside this task.

**Task 7.6D implementation and evidence are ready for review and a later authorized commit. Production security readiness is not granted.** Nothing is staged or committed.
