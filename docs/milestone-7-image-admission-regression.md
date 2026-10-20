# Milestone 7 Task 7.12 — Image admission regression

Date: 2026-10-19, America/New_York. Scope: admission-worker diagnostics, local error classification, lifecycle cleanup and regression verification only. No v3 activation/integration, consensus change, compression-policy change, migration, chain reset, deployment, commit, push, merge or subsequent task.

## Repository verification

- Branch: `Compression-State-Bloat-and-Node-Economics`.
- Starting and ending HEAD: `3a93bff28a13ac376354ac23d989799fabc6a2d3`.
- Task 7.11 is separately committed at that HEAD (`Milestone 7 Task 7.11: implement isolated canonical v3 SQLite storage`).
- Initial tracked/untracked worktree was clean. No repository/ancestor AGENTS.md was found. Final changes are unstaged and limited to the files/evidence below.
- Read the Task 6.3 validator documentation, Task 7.11 regression record, and Task 7.6C/7.6D isolation documentation. Inspection followed admission, its worker, API exception boundary and related tests; no active consensus implementation was edited.

## Exact baseline and root cause

The documented Task 7.11 historical selection reproduced **23 failed, 92 passed in 11.99 seconds**, on unchanged HEAD. Every failure stopped during valid image fixture admission with `TechnicalMediaValidationError: MALFORMED_MEDIA`, before its intended storage/block assertions. Exact node IDs are listed below and preserved with traces in `benchmarks/milestone_7_task_7_12_baseline.txt`.

The direct worker trace in `benchmarks/milestone_7_task_7_12_diagnostic.txt` shows the first error at **os.chdir(empty_dir)**, before Pillow opens any bytes:

```text
PermissionError: [WinError 5] Access is denied:
C:\Users\mattk\AppData\Local\Packages\sandbox.{4aa64a00-4b18-49fc-a77b-b956f711008f}\AC\Temp\zoidberg-media-worker-epjmyam1
```

TemporaryDirectory cleanup then also fails at rmdir/chmod, potentially replacing the original exception. The process-pool remote traceback preserves both. The broad exception handler in validate_media_bytes converted the resulting PermissionError into MALFORMED_MEDIA. This is an execution-environment error, not a malformed fixture or v3 regression.

The same environment allowed directory creation, stat and listing but denied changing into/removing the generated directory. Python stat reported mode 16895 (directory plus 0777); that does **not** establish effective Windows ACL access. An attempted later ACL read found the per-command sandbox path no longer present (`..._acl.txt`); no specific denying ACE is claimed. The exact observed failing operation, OS error and paths are recorded; permissions were never changed.

An independent control, still using the **unchanged implementation**, set only process-local TEMP and TMP to an existing directory under the authorized workspace. The same 115 tests then passed in 20.33 seconds (`..._environment_control.txt`). This isolates temporary-root accessibility as the cause of the 23 failures. Changing tempfile configuration grants no additional OS permissions.

The new diagnostic runner reproduces the raw worker PermissionError and records **worker exit code 0** after pool shutdown: Python transported a task exception; the worker did not crash. With the bad root, the repaired public validator raises **MediaValidationUnavailable**, preserving the exception chain and issuing no evidence verdict (`..._after_diagnostic.txt`). With the configured root it decodes, exits 0, cleans up and admits (`..._configured_diagnostic.txt`). Deliberate crash tests instead exit the child with 23 and verify BrokenProcessPool becomes local unavailability. A timeout remains the existing RESOURCE_LIMIT_TERMINATED local-defense result.

## Execution path and correction

Before: upload/service or file-submission entry → validate_media_bytes → byte/type/MIME/container/dimension checks → _run_isolated_decoder → fresh ProcessPoolExecutor child (spawn on Windows, fork on POSIX) → attempted POSIX RLIMIT_AS → child creates TemporaryDirectory → chdir → Pillow verify, reopen, all-frame RGBA load → restore cwd and delete directory → future.result. Timeout terminates workers; all other exceptions previously became MALFORMED_MEDIA.

After:

1. The parent creates the unique empty directory under the operator's normal tempfile root, then starts the same isolated child. No media-derived path or automatic alternate directory is used.
2. The child retains its POSIX memory-limit setup, enters that directory, verifies and fully loads the same bytes/frames using the same Pillow/type checks, and restores its cwd. Filesystem operations after memory-limit setup include chdir, trusted Pillow plugin/library activity and cwd restoration. This admission worker installs no syscall/filesystem/network confinement policy.
3. Only explicit decoder-content failures become the private, pickle-safe _MalformedImageError and then MALFORMED_MEDIA. PermissionError, OSError carrying errno/winerror, MemoryError, unexpected exceptions, startup failures, broken pools and cleanup failures become MediaValidationUnavailable (RuntimeError, not ValueError), with the cause retained.
4. The parent shuts down/reaps the executor before deleting its directory, including after forced termination or crash. A cleanup failure withholds acceptance and reports local unavailability. Setup/submission failures also leave through the same boundary.
5. The FastAPI exception boundary returns HTTP **503**, code **MEDIA_VALIDATION_UNAVAILABLE**, without exposing private paths. It does not turn a local failure into a client malformed-media response. Direct callers receive the typed exception.
6. Timeout retains the existing reason RESOURCE_LIMIT_TERMINATED and local_resource_defense_failure=true. It refuses local admission; it does not assert malformed media or invalidate an already-certified block.

The affected local upload/file-submission service paths use the same worker outside tests, so genuine submissions encounter the same unavailability when their runtime temporary root is inaccessible. Incoming certified-block consensus validation is not routed through this local worker; no block-consensus verdict, evidence identity for accepted bytes, originality decision or admissibility rule was changed.

## Files modified

- `media_technical_validation.py`: typed decoder/local error boundary; parent-owned directory lifecycle; reaping before cleanup.
- `api_runtime.py`: specific 503 exception handler.
- `tests/test_milestone_7_task_7_12_image_admission.py`: 19 focused cases, including four valid formats, truncation, corrupt compressed stream, MIME mismatch, real child permission/crash/timeout, decode-stage OS errors, temp setup/cleanup failures, separate process/empty decode cwd, and public 503/no persistence.
- `tests/test_milestone_6_task_6_3_technical_media_validation.py`: change only the injected RuntimeError assertion to expect local unavailability. This intentionally corrects the old test's error-classification contract; no historical storage/protocol fixture or failing block assertion was rewritten.
- `scripts/milestone_7_task_7_12_diagnose.py`: offline reproducible runtime/path/worker-exit/cleanup diagnostics, no chain access.
- This document and `benchmarks/milestone_7_task_7_12_*.txt`: evidence logs, including unsuccessful environment invocations.

## Reproduction commands

From the repository root, first reproduce the original baseline on the starting commit, using the default sandbox TEMP/TMP. Do not reset a worktree with review changes to reproduce it. The command is the same historical selection below, before the temporary-root configuration. The baseline log preserves that original run.

The operational correction is explicit, process-local standard tempfile configuration. Create an operator-owned root on an already authorized filesystem; do not use client filenames, permissive ACL grants or an automatic fallback:

```powershell
New-Item -ItemType Directory -Force temp/task712-runtime | Out-Null
$env:TEMP=(Resolve-Path temp/task712-runtime).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -B scripts/milestone_7_task_7_12_diagnose.py
.\.venv\Scripts\python.exe -B -m pytest tests/test_protocol_v1.py tests/test_protocol_v1_golden_vectors.py tests/test_protocol_v1_native_transfers.py tests/blockchain/test_task_3_5_validator_quorum_finality.py::test_validator_quorum_is_ceiling_of_two_thirds tests/storage/test_sqlite_storage_backend.py tests/storage/test_storage_tools.py -q --tb=short -p no:cacheprovider --basetemp=temp/task712-review-regression
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_12_image_admission.py tests/test_milestone_6_task_6_3_technical_media_validation.py -q --tb=short -p no:cacheprovider --basetemp=temp/task712-review-admission
.\.venv\Scripts\python.exe -B -m pytest tests/test_milestone_7_task_7_11_storage.py tests/test_milestone_7_task_7_10c_v3.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py tests/test_milestone_7_task_7_6c_isolation.py tests/test_milestone_7_task_7_6d_linux_isolation.py tests/test_milestone_7_task_7_6d_evidence.py -q --tb=short -p no:cacheprovider --basetemp=temp/task712-review-storage
.\.venv\Scripts\python.exe -B -m pytest tests/blockchain/test_protocol_v1_block_format.py tests/blockchain/test_protocol_v1_genesis.py -q --tb=short -p no:cacheprovider --basetemp=temp/task712-review-blocks
```

For diagnostics without changing process environment, use `--temp-root temp/task712-runtime`. Without that option and without TEMP/TMP configuration, the original inaccessible sandbox root still correctly reports unavailability. There is no application fallback or global/user environment edit.

The outer Codex Windows sandbox also stalled Python asyncio's internal loopback socketpair setup for TestClient (stack: socket.accept → _fallback_socketpair → ProactorEventLoop). Those test attempts were stopped. The API-containing tests were rerun successfully in the host test environment; the application worker implementation and restrictions were unchanged. Non-API historical/storage/block tests also passed under the outer sandbox with the explicit temp configuration. This host-run distinction does not imply OS network confinement exists in the admission worker.

Ubuntu WSL2 uses the existing repository-local Task 7.6D runtime (no system package changes). Inside Ubuntu, from `/mnt/c/Users/mattk/ZoidbergChain`:

```sh
temp/task76d-venv/bin/python -B -m pytest tests/test_milestone_7_task_7_12_image_admission.py -k 'not public_upload' -q --tb=short -p no:cacheprovider --basetemp=temp/task712-linux-review
ZOIDBERG_TASK76D_INPUTS=temp/task76d-inputs.json temp/task76d-venv/bin/python -B -m pytest tests/test_milestone_7_task_7_6d_linux_isolation.py tests/test_milestone_7_task_7_6d_evidence.py tests/test_milestone_7_task_7_6_decoder.py tests/test_milestone_7_task_7_6a_sequences.py -q --tb=short -p no:cacheprovider --basetemp=temp/task712-linux-isolation-review
```

The portable input bundle is the existing ignored Task 7.6D bundle, verified against the tracked manifest by get_cases. Its documented export command, if needed on the reference Windows environment, is `.\.venv\Scripts\python.exe scripts/milestone_7_task_7_6d_isolation.py --export-inputs temp/task76d-inputs.json`. Do not regenerate or change the frozen manifest to match Linux encoders.

## Before/after verification

| Selection / log suffix | Result | Notes |
| --- | --- | --- |
| Unchanged HEAD, default sandbox temp / baseline | 23 failed, 92 passed; 11.99 s | Exact historical reproduction |
| Unchanged code, configured temp / environment_control | 115 passed; 20.33 s | Environment-only control |
| Repaired code, historical selection / regression | 115 passed; 20.91 s | All 23 original failures eliminated |
| Initial 16 new tests plus existing Task 6.3 / focused | 66 passed; 7.52 s | Host API-capable test run; includes 50 existing cases |
| Final expanded Task 7.12 / final_focused | 19 passed; 5.29 s | Windows host, real workers and API |
| Task 7.11/7.10C/7.6/7.6A/C/D/evidence / storage_isolation | 559 passed, 193 skipped; 123.17 s | Windows; platform skips explicit |
| Additional protocol block-format/genesis / block_format | 32 passed; 5.79 s | Windows, unchanged fixtures/assertions |
| Final expanded Task 7.12 / linux | 18 passed, 1 deselected; 2.30 s | Ubuntu WSL2; API case excluded |
| Linux decoder/isolation / linux_isolation | 375 passed, 1 failed; 49.71 s | Initial invocation omitted documented bundle setting |
| Exact failed Linux corpus node / linux_corpus | 1 passed; 8.04 s | Corrected input setting; all 36 manifest originals reconstruct |

The Linux initial failure was test_corpus_exact_reconstruction, failing the pre-decoder manifest assertion when regenerating image bytes with Linux native encoders. Replaying the existing manifest-matching originals/descriptors with ZOIDBERG_TASK76D_INPUTS passed, without source or fixture edits. Effective final Linux selection: 376 passing isolation/decoder cases across the initial run and corrected single-node rerun. This invocation issue is not counted as a fixed admission defect. No unresolved failure remains in the properly configured selections; unrelated suites were not claimed fixed. Counts across rows overlap and must not be summed as unique coverage.

Runtime: Windows 11 build 26200, CPython 3.13.5 AMD64, Pillow 12.3.0, pytest 8.4.1. Ubuntu WSL2: Linux 6.6.87.2-microsoft-standard-WSL2 x86_64, non-root uid 1000, CPython 3.12.3, Pillow 12.3.0, pytest 8.4.1. Windows uses spawn; Linux uses fork for the admission worker. The Linux web/chain runtime lacks FastAPI; the HTTP case and full historical storage/chain selection were not run there. Native Ubuntu production verification is not claimed.

## Security implications and remaining limitations

- No isolated-worker bypass, format/size relaxation, decoder shortcut, network policy change or filesystem permission grant. Exact image bytes, strict MIME/container validation, full-frame decoding, evidence rules and originality/admissibility remain intact. The worker cwd is still a unique empty temporary directory. Fixture tests use standard writable temporary roots, not a sandbox-disable switch.
- The existing admission worker is weaker than the isolated **v3 compression prototype**. It has process isolation, a cwd and best-effort POSIX RLIMIT_AS, but no OS filesystem/network denial, secret scrubbing, Windows Job Object memory enforcement or mandatory hard-limit setup failure. Those are existing documented operational/security limitations; this task neither invents guarantees nor redesigns containment. The stronger v3 prototype was not integrated or edited; its platform containment suites pass.
- Inaccessible/misconfigured temporary storage still prevents admission, now explicitly. Operators must provision a usable private temp root for the service identity before accepting images. Failed cleanup in a denied root can leave a directory for the environment owner; the validator does not chmod, broaden access, hide the error or claim successful cleanup. Host termination/power loss can also leave temp state.
- Pool termination/reaping still relies on the existing executor process handles; a hostile/failed OS can prevent timely cleanup. This is not production containment signoff.
- Timeouts remain local-defense refusals with their existing flag/reason. Consumers must retain this distinction from deterministic media invalidity. No new consensus rejection path was introduced.
- Full-suite testing, Linux web/storage parity, native Ubuntu production verification and a broader admission sandbox redesign remain outside this task. API tests require a functioning local event-loop socket environment.

**Review decision:** Task 7.12 is ready for review and commit, with no commit performed. The reproduced image-admission regression no longer blocks progress toward active v3 integration **when the validation environment has a usable configured temporary root**. This is an image-admission regression conclusion only; it does not authorize active integration or close the existing security/production gates. No next task was started.

## Exact original failing node IDs

```text
FAILED tests/storage/test_sqlite_storage_backend.py::test_blockchain_round_trip_persists_core_entities_sqlite
FAILED tests/storage/test_storage_tools.py::test_backup_file_is_created_and_sanitized[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_backup_file_is_created_and_sanitized[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_export_includes_core_state_and_excludes_private_keys_by_default[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_export_includes_core_state_and_excludes_private_keys_by_default[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_export_private_keys_requires_development_and_explicit_flag
FAILED tests/storage/test_storage_tools.py::test_export_private_keys_rejected_outside_development
FAILED tests/storage/test_storage_tools.py::test_import_round_trip_into_empty_backend[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_import_round_trip_into_empty_backend[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_export_and_import_preserve_native_transaction_state[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_export_and_import_preserve_native_transaction_state[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_import_refuses_overwrite_by_default
FAILED tests/storage/test_storage_tools.py::test_import_rejects_snapshot_with_mutated_public_testnet_v1_genesis
FAILED tests/storage/test_storage_tools.py::test_import_creates_backup_before_overwrite
FAILED tests/storage/test_storage_tools.py::test_import_rejects_wrong_network_without_override
FAILED tests/storage/test_storage_tools.py::test_import_runs_integrity_check
FAILED tests/storage/test_storage_tools.py::test_dry_run_does_not_write_files
FAILED tests/storage/test_storage_tools.py::test_backup_snapshot_can_be_imported_as_restore[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_backup_snapshot_can_be_imported_as_restore[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_imported_state_supports_follow_on_app_workflow[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_imported_state_supports_follow_on_app_workflow[_sqlite_backend]
FAILED tests/storage/test_storage_tools.py::test_node_a_backup_export_import_do_not_affect_node_b[_json_backend]
FAILED tests/storage/test_storage_tools.py::test_node_a_backup_export_import_do_not_affect_node_b[_sqlite_backend]
```
