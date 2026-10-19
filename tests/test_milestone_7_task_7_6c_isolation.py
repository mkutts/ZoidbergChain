"""Real Windows Job Object and IPC tests; other platforms explicitly untested."""
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
from ctypes import wintypes as W
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from codec_prototype import isolated_decoder as isolated
from codec_prototype import strict_decoder as codec
from codec_prototype import worker_ipc as ipc
from scripts.milestone_7_task_7_6_vectors import descriptor, compress

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests/helpers/decoder_worker_fixture.py"
SITE = str(Path(sys.prefix) / "Lib/site-packages")
WINDOWS = pytest.mark.skipif(os.name != "nt", reason="Windows controls require actual Windows execution")
RAW = ipc.canonical(descriptor(b"abc", b"abc", codec_id="identity"))


class Controlled(isolated.IsolatedDecoder):
    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.spawned = threading.Event()
        self.process = None
        self.processes = []

    def _command(self):
        return [sys._base_executable, "-I", "-u", str(HELPER), SITE, self.mode]

    def _spawn(self):
        self.process = super()._spawn()
        self.processes.append(self.process)
        self.spawned.set()
        return self.process


def assert_local_clean(result):
    assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE
    assert result.original is None and result.stage is None and result.code is None
    assert result.metrics["reaped"] is True
    assert result.metrics["exit_code"] is not None


@pytest.mark.parametrize("header,body_cap", [(ipc.PREFIX.pack(ipc.MAGIC, 1025, 0), 0),
    (ipc.PREFIX.pack(ipc.MAGIC, 1, ipc.MAX_REQUEST + 1), ipc.MAX_REQUEST),
    (ipc.PREFIX.pack(b"BAD!", 1, 0), 0)])
def test_ipc_lengths_reject_before_body_allocation(header, body_cap):
    class PrefixOnly(io.BytesIO):
        def readinto(self, target):
            assert len(target) == ipc.PREFIX.size
            return super().readinto(target)
    with pytest.raises(ipc.IPCError):
        ipc.read_message(PrefixOnly(header), body_cap)


@pytest.mark.parametrize("raw", [b'{"v":1,"v":1}', b'{"v":true}', b'{"v":NaN}',
    b'{"v":{"x":1}}', b'[]', b'{"v":1} ', b'\xff', b'{"v":"\\u0031"}'])
def test_untrusted_metadata_is_flat_canonical_and_closed_at_boundary(raw):
    with pytest.raises(ipc.IPCError):
        ipc.read_message(io.BytesIO(ipc.PREFIX.pack(ipc.MAGIC, len(raw), 0) + raw), 0)


def test_partial_pipe_writes_are_completed():
    class ShortWrites(io.BytesIO):
        def write(self, value):
            return super().write(value[:3])
    stream = ShortWrites()
    ipc.write_message(stream, dict(v=1, kind="ready"), b"abc")
    stream.seek(0)
    assert ipc.read_message(stream, 3) == (dict(v=1, kind="ready"), b"abc")


@pytest.mark.parametrize("limits", [dict(cpu_seconds=float("nan")), dict(wall_seconds=float("inf")),
    dict(cpu_seconds=True), dict(memory_bytes=0), dict(startup_seconds=100)])
def test_operational_configuration_cannot_disable_bounds(limits):
    with pytest.raises(ValueError):
        isolated.Limits(**limits)


def test_oversized_and_invalid_json_reject_before_dispatch(monkeypatch):
    with isolated.IsolatedDecoder() as pool:
        monkeypatch.setattr(pool, "_spawn", lambda: pytest.fail("invalid transport dispatched"))
        for raw, code in ((b"x" * (ipc.MAX_REQUEST + 1), "json_size"), (b'{} ', "noncanonical_json"),
                          (b'{"x":{}}', "json_shape")):
            result = pool.validate(raw)
            assert (result.status, result.stage, result.code) == (isolated.Status.INVALID, "descriptor", code)


def test_unsupported_platform_never_falls_back_to_parent_decode(monkeypatch):
    monkeypatch.setattr(isolated, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(isolated, "sys", SimpleNamespace(platform="darwin"))
    result = isolated.IsolatedDecoder().validate(RAW)
    assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE and result.reason == "unsupported_platform"


@WINDOWS
def test_parent_never_reconstructs_encoded_or_original_bytes(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("parent decoded untrusted media")
    for name in ("decode", "_payload", "_backend"):
        monkeypatch.setattr(codec, name, forbidden)
    with isolated.IsolatedDecoder() as pool:
        result = pool.validate((ROOT / "tests/fixtures/milestone_7_codec_v1/zstd-default.json").read_bytes())
        assert result.status == isolated.Status.VALID and result.original
        assert result.metrics["reaped"] is True
        assert result.metrics["enforced_active_processes"] == 1
        assert result.metrics["enforced_affinity"].bit_count() == 1
        assert result.metrics["enforced_memory_bytes"] == 128 * 1024**2
        assert result.metrics["enforced_user_cpu_ns"] == 5_000_000_000


VECTORS = []
for folder in ("milestone_7_codec_v1", "milestone_7_codec_v2"):
    directory = ROOT / "tests/fixtures" / folder
    VECTORS += [(directory, item) for item in json.loads((directory / "manifest.json").read_bytes())["vectors"]]


@WINDOWS
@pytest.mark.parametrize("directory,item", VECTORS, ids=[v[1]["id"] for v in VECTORS])
def test_all_frozen_vectors_keep_worker_classification_and_bytes(directory, item):
    raw = (directory / item["descriptor_path"]).read_bytes()
    desc = codec.parse_descriptor(raw)
    try:
        expected = codec.decode(desc)
    except codec.CodecReject as exc:
        expected = (exc.stage, exc.code)
    with isolated.IsolatedDecoder() as pool:
        result = pool.validate(raw)
    if type(expected) is tuple:
        assert (result.status, result.stage, result.code) == (isolated.Status.INVALID, *expected)
    else:
        assert result.status == isolated.Status.VALID, (result.reason, result.metrics)
        assert result.original == expected.original == (directory / item["original_path"]).read_bytes()
    assert result.metrics["reaped"] is True


@WINDOWS
def test_full_corpus_reconstructs_through_worker():
    from scripts.milestone_7_task_7_3_corpus import build_samples, MANIFEST_PATH
    manifest = {r["id"]: r for r in json.loads(MANIFEST_PATH.read_bytes())["samples"]}
    with isolated.IsolatedDecoder() as pool:
        for sample in build_samples():
            original = sample["bytes"]
            assert hashlib.sha256(original).hexdigest() == manifest[sample["id"]]["sha256"]
            raw = ipc.canonical(descriptor(original, compress(original), mime=sample["mime_type"]))
            result = pool.validate(raw)
            assert result.status == isolated.Status.VALID, (sample["id"], result.reason, result.metrics)
            assert result.original == original and result.metrics["reaped"] is True


@WINDOWS
@pytest.mark.parametrize("mode", ["crash", "oversized", "truncated", "malformed", "duplicate", "unknown_status",
    "wrong_id", "wrong_request", "wrong_hash", "wrong_size", "excess_body", "extra_field", "trailing", "exit_after_reply"])
def test_crashes_and_bad_responses_are_local_without_exposing_bytes(mode):
    with Controlled(mode) as pool:
        assert_local_clean(pool.validate(RAW))


@WINDOWS
@pytest.mark.parametrize("mode,reason", [("hang", "timeout"), ("close_then_hang", "timeout"), ("startup_hang", "startup_timeout")])
def test_hang_deadlines_kill_reap_and_do_not_reject_media(mode, reason):
    startup = 0.3 if mode == "startup_hang" else 3
    with Controlled(mode, limits=isolated.Limits(startup_seconds=startup, wall_seconds=0.2)) as pool:
        result = pool.validate(RAW)
        assert_local_clean(result)
        assert result.reason == reason
    with isolated.IsolatedDecoder() as healthy:
        assert healthy.validate(RAW).status == isolated.Status.VALID


@WINDOWS
@pytest.mark.parametrize("action", ["cancel", "terminate", "close"])
def test_cancellation_external_termination_and_shutdown(action):
    pool, cancel = Controlled("hang"), threading.Event()
    with ThreadPoolExecutor(max_workers=1) as threads:
        future = threads.submit(pool.validate, RAW, cancel=cancel)
        try:
            assert pool.spawned.wait(3)
            if action == "cancel":
                cancel.set()
            elif action == "terminate":
                pool.process.terminate()
            else:
                pool.close()
            result = future.result(timeout=5)
            assert_local_clean(result)
        finally:
            cancel.set()
            pool.close()
    assert pool.validate(RAW).reason == "closed"


@WINDOWS
def test_global_concurrency_is_shared_across_coordinators_and_recovers():
    pools = [Controlled("hang", max_workers=2) for _ in range(3)]
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=2) as threads:
        futures = [threads.submit(pool.validate, RAW, cancel=cancel) for pool in pools[:2]]
        try:
            assert all(p.spawned.wait(3) for p in pools[:2])
            for _ in range(20):
                result = pools[2].validate(RAW)
                assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE and result.reason == "saturated"
            assert not pools[2].spawned.is_set()
        finally:
            cancel.set()
            for future in futures:
                assert_local_clean(future.result(timeout=5))
            for pool in pools:
                pool.close()
    with isolated.IsolatedDecoder() as pool:
        assert pool.validate(RAW).status == isolated.Status.VALID


@WINDOWS
def test_failure_recovery_does_not_retry_or_reuse_processes():
    with Controlled("crash") as pool:
        pids = []
        for _ in range(3):
            result = pool.validate(RAW)
            assert_local_clean(result)
            pids.append(result.metrics["pid"])
        pool._command = lambda: isolated.IsolatedDecoder._command(pool)
        result = pool.validate(RAW)
        assert result.status == isolated.Status.VALID and result.original == b"abc"
        # Windows may reuse PIDs; retained launcher objects prove four separate
        # launches and closed native handles without relying on PID uniqueness.
        assert len(pool.processes) == 4
        assert all(p.handle is None and p.job is None for p in pool.processes)
    assert not [t for t in threading.enumerate() if t.name.startswith("decoder-ipc-")]


@WINDOWS
def test_startup_control_failure_is_local_and_retry_is_explicit(monkeypatch):
    with isolated.IsolatedDecoder() as pool:
        spawn = pool._spawn
        attempts = []
        def unavailable():
            attempts.append(1)
            raise OSError("controlled control-setup failure")
        monkeypatch.setattr(pool, "_spawn", unavailable)
        result = pool.validate(RAW)
        assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE and result.original is None
        assert len(attempts) == 1
        monkeypatch.setattr(pool, "_spawn", spawn)
        assert pool.validate(RAW).status == isolated.Status.VALID


@WINDOWS
def test_uncertain_cleanup_quarantines_capacity(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(isolated, "_GLOBAL_SLOTS", slots)
    with isolated.IsolatedDecoder() as pool:
        spawn = pool._spawn
        def with_failed_accounting():
            process = spawn()
            def failed_metrics():
                raise OSError("controlled accounting failure after reap")
            process.metrics = failed_metrics
            return process
        monkeypatch.setattr(pool, "_spawn", with_failed_accounting)
        result = pool.validate(RAW)
        assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE and result.reason == "cleanup_failure"
        assert result.original is None and not result.metrics["reaped"]
        assert pool.validate(RAW).reason == "saturated"
        assert not slots.acquire(blocking=False)


@WINDOWS
def test_precancel_does_not_spawn_and_releases_capacity(monkeypatch):
    cancel = threading.Event()
    cancel.set()
    with isolated.IsolatedDecoder() as pool:
        spawn = pool._spawn
        monkeypatch.setattr(pool, "_spawn", lambda: pytest.fail("cancelled request spawned"))
        assert pool.validate(RAW, cancel=cancel).reason == "cancelled"
        monkeypatch.setattr(pool, "_spawn", spawn)
        assert pool.validate(RAW).status == isolated.Status.VALID


@WINDOWS
def test_repeated_jobs_release_native_parent_handles():
    k = C.WinDLL("kernel32", use_last_error=True)
    k.GetCurrentProcess.restype = W.HANDLE
    k.GetProcessHandleCount.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    def count():
        result = W.DWORD()
        assert k.GetProcessHandleCount(k.GetCurrentProcess(), C.byref(result))
        return result.value
    with isolated.IsolatedDecoder() as pool:
        assert pool.validate(RAW).status == isolated.Status.VALID
        before = count()
        for _ in range(5):
            assert pool.validate(RAW).status == isolated.Status.VALID
        assert count() <= before + 2


@WINDOWS
def test_job_memory_and_child_process_limits_are_enforced():
    for mode, reason in (("allocate", "worker_memory_limit_confirmed"), ("spawn_child", "worker_child_limit_confirmed")):
        with Controlled(mode, limits=isolated.Limits(memory_bytes=32 * 1024**2)) as pool:
            result = pool.validate(RAW)
            assert_local_clean(result)
            assert result.reason == reason
            assert result.metrics["peak_job_commit_bytes"] <= 32 * 1024**2


@WINDOWS
def test_cpu_watchdog_and_job_budget_terminate_spin_before_wall_watchdog():
    with Controlled("spin", limits=isolated.Limits(cpu_seconds=0.2, wall_seconds=5)) as pool:
        result = pool.validate(RAW)
        assert_local_clean(result)
        assert result.reason == "cpu_limit" or (result.reason != "timeout" and result.metrics["exit_code"] != 71)
        assert result.metrics["enforced_user_cpu_ns"] == 200_000_000
        assert result.metrics["process_user_ns"] >= 180_000_000


@WINDOWS
def test_worker_rejects_oversized_ipc_request_without_body_read():
    with isolated.IsolatedDecoder() as pool:
        process = pool._spawn()
        try:
            assert ipc.read_message(process.stdout, 0) == (dict(v=1, kind="ready"), b"")
            process.stdin.write(ipc.PREFIX.pack(ipc.MAGIC, 1, ipc.MAX_REQUEST + 1))
            process.stdin.close()
            assert process.wait(3) != 0
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(2)
            process.close()


@WINDOWS
def test_parent_death_closes_job_and_kills_worker():
    fixture = ROOT / "tests/fixtures/milestone_7_codec_v1/zstd-default.json"
    parent = subprocess.Popen([sys._base_executable, "-I", "-u", str(HELPER), SITE, "controller", str(fixture)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    handle = None
    k = C.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.argtypes, k.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
    k.WaitForSingleObject.argtypes, k.WaitForSingleObject.restype = [W.HANDLE, W.DWORD], W.DWORD
    k.CloseHandle.argtypes = [W.HANDLE]
    try:
        # Bound the test's read too: a broken launcher must not hang the suite.
        with ThreadPoolExecutor(max_workers=1) as reader:
            line = reader.submit(parent.stdout.readline)
            try:
                pid = int(line.result(timeout=5))
            except BaseException:
                parent.kill()
                raise
        handle = k.OpenProcess(0x100000, False, pid)
        assert handle
        parent.kill()
        parent.wait(timeout=3)
        assert k.WaitForSingleObject(handle, 3000) == 0
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        parent.stdout.close()
        if handle:
            k.CloseHandle(handle)


def test_measurement_artifact_matches_worker_sources_and_replay():
    report = json.loads((ROOT / "benchmarks/milestone_7_task_7_6c_results.json").read_bytes())
    assert report["baseline_head"] == "86838da59d41964d8a0714720bdbf6d44a98a239"
    for path, digest in report["source_sha256"].items():
        # This immutable artifact describes the committed 7.6C sources. Later
        # platform work must not rewrite its historical measurements/hashes.
        historical = subprocess.check_output(["git", "show", f"8607636:{path}"], cwd=ROOT)
        assert hashlib.sha256(historical).hexdigest() == digest
    assert report["golden"]["counts"] == {"VALID": 42, "INVALID": 110}
    assert report["corpus"]["samples"] == 36
    assert all(row["exact_bytes"] for row in report["corpus"]["rows"])
    assert report["global_concurrency"] == 2 and report["queued_requests"] == 0
    assert report["independent_decoder"] is False and report["linux_enforcement"] is False
    assert all(row["status"] == "INDETERMINATE_LOCAL_FAILURE" and row["metrics"]["reaped"] for row in report["faults"])
    assert len(report["per_case"]) == 7
    assert all(row["exact_reconstruction"] for row in report["per_case"])
