"""Actual Linux controls: skipped explicitly elsewhere, no simulated evidence."""
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import sysconfig
import threading
import time

import pytest

from codec_prototype import isolated_decoder as isolated
from codec_prototype import worker_ipc as ipc
from scripts.milestone_7_task_7_6_vectors import descriptor, compress

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests/helpers/linux_decoder_worker_fixture.py"
RAW = ipc.canonical(descriptor(b"abc", b"abc", "identity"))
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="requires an actual Linux kernel")


class Controlled(isolated.IsolatedDecoder):
    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode, self.processes = mode, []
        self.spawned = threading.Event()

    def _command(self):
        return [sys.executable, "-I", "-u", str(HELPER), str(os.getpid()),
                str(self.limits.memory_bytes), str(self.limits.cpu_seconds),
                sysconfig.get_path("purelib"), self.mode, str(threading.get_native_id())]

    def _spawn(self):
        process = super()._spawn()
        self.processes.append(process)
        self.spawned.set()
        return process


def clean_local(result):
    assert result.status == isolated.Status.INDETERMINATE_LOCAL_FAILURE, result
    assert result.original is None and result.stage is None and result.code is None
    assert result.metrics["reaped"] and result.metrics["exit_code"] is not None
    assert not Path(f"/proc/{result.metrics['pid']}").exists()


def test_parent_never_decodes(monkeypatch):
    def forbidden(*args):
        pytest.fail("parent decoded media")
    for name in ("decode", "_payload", "_backend"):
        monkeypatch.setattr(isolated.codec, name, forbidden)
    with isolated.IsolatedDecoder() as pool:
        result = pool.validate((ROOT / "tests/fixtures/milestone_7_codec_v1/zstd-default.json").read_bytes())
    assert result.status == isolated.Status.VALID and result.metrics["reaped"]


VECTORS = [(ROOT / "tests/fixtures" / folder, item)
           for folder in ("milestone_7_codec_v1", "milestone_7_codec_v2")
           for item in json.loads((ROOT / "tests/fixtures" / folder / "manifest.json").read_bytes())["vectors"]]


@pytest.mark.parametrize("directory,item", VECTORS, ids=[v[1]["id"] for v in VECTORS])
def test_frozen_vectors(directory, item):
    raw = (directory / item["descriptor_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["descriptor_sha256"]
    with isolated.IsolatedDecoder() as pool:
        result = pool.validate(raw)
    if item.get("profile_expected", item["expected"]) == "accept":
        assert result.status == isolated.Status.VALID, result
        assert result.original == (directory / item["original_path"]).read_bytes()
    else:
        stage, code = item["stage"], item["code"]
        if item["id"] == "offset-exceeds-declared-window":
            stage, code = "decode", "window_offset"
        assert (result.status, result.stage, result.code) == (isolated.Status.INVALID, stage, code)
    assert result.metrics["reaped"]


def test_corpus_exact_reconstruction():
    from scripts.milestone_7_task_7_6d_isolation import get_cases
    bundle = os.environ.get("ZOIDBERG_TASK76D_INPUTS")
    samples, _, _ = get_cases(bundle)
    with isolated.IsolatedDecoder() as pool:
        for sample in samples:
            original = sample["original"]
            result = pool.validate(sample["raw"])
            assert result.status == isolated.Status.VALID, (sample["id"], result)
            assert result.original == original and result.metrics["reaped"]


@pytest.mark.parametrize("mode,reason", [("filesystem", "worker_filesystem_denied"),
    ("network", "worker_network_denied"), ("spawn_child", "worker_child_denied"),
    ("privilege", "worker_privilege_denied"), ("descriptors", "worker_descriptors_closed"),
    ("limits", "worker_limits_sealed"), ("allocate", "worker_memory_limit_confirmed"),
    ("allocate_native", "worker_native_memory_denied"),
    ("missing_seccomp", "linux_seccomp_unavailable")])
def test_controls_enforced(mode, reason):
    with Controlled(mode, limits=isolated.Limits(memory_bytes=48 * 1024**2)) as pool:
        result = pool.validate(RAW)
    clean_local(result)
    assert result.reason == reason


@pytest.mark.parametrize("mode", ["crash", "oversized", "truncated", "malformed", "duplicate", "unknown_status",
    "wrong_id", "wrong_request", "wrong_hash", "wrong_size", "excess_body", "extra_field", "trailing", "exit_after_reply"])
def test_faults_and_malformed_ipc(mode):
    with Controlled(mode) as pool:
        clean_local(pool.validate(RAW))


@pytest.mark.parametrize("mode,reason", [("hang", "timeout"), ("startup_hang", "startup_timeout"),
                                       ("close_then_hang", "timeout")])
def test_hang_watchdogs(mode, reason):
    limits = isolated.Limits(wall_seconds=0.2, startup_seconds=0.5 if mode == "startup_hang" else 5)
    with Controlled(mode, limits=limits) as pool:
        result = pool.validate(RAW)
    clean_local(result)
    assert result.reason == reason


def test_cpu_budget_and_native_accounting():
    with Controlled("spin", limits=isolated.Limits(cpu_seconds=0.2, wall_seconds=4)) as pool:
        result = pool.validate(RAW)
    clean_local(result)
    assert result.reason == "cpu_limit" or result.metrics["exit_code"] == -signal.SIGKILL
    assert result.reason != "timeout"
    assert result.metrics["process_user_ns"] + result.metrics["process_kernel_ns"] >= 180_000_000
    assert result.metrics["peak_rss_bytes"] > 0


def test_kernel_cpu_limit_without_coordinator_sampling():
    with Controlled("spin", limits=isolated.Limits(cpu_seconds=0.2, wall_seconds=4)) as pool:
        process = pool._spawn()
        try:
            assert ipc.read_message(process.stdout, 0) == (dict(v=1, kind="ready"), b"")
            ipc.write_message(process.stdin, dict(v=1, kind="request", id="1" * 32,
                request_sha256=hashlib.sha256(RAW).hexdigest()), RAW, ipc.MAX_REQUEST)
            process.stdin.close()
            assert process.wait(4) == -signal.SIGKILL
            metrics = process.metrics()
            assert metrics["process_user_ns"] + metrics["process_kernel_ns"] >= 900_000_000
        finally:
            process.close()


def test_kernel_state_before_any_request():
    with isolated.IsolatedDecoder() as pool:
        process = pool._spawn()
        try:
            assert ipc.read_message(process.stdout, 0) == (dict(v=1, kind="ready"), b"")
            status = Path(f"/proc/{process.pid}/status").read_text()
            for value in ("NoNewPrivs:\t1", "Seccomp:\t2", "CapEff:\t0000000000000000",
                          "CapPrm:\t0000000000000000", "CapInh:\t0000000000000000"):
                assert value in status
            limits = Path(f"/proc/{process.pid}/limits").read_text()
            assert "134217728" in next(line for line in limits.splitlines() if line.startswith("Max address space"))
            assert "16" in next(line for line in limits.splitlines() if line.startswith("Max open files"))
            assert "1" in next(line for line in limits.splitlines() if line.startswith("Max processes"))
            assert len(os.sched_getaffinity(process.pid)) == 1
            assert os.getpgid(process.pid) == os.getsid(process.pid) == process.pid
        finally:
            process.close()


@pytest.mark.parametrize("action", ["cancel", "terminate", "close"])
def test_explicit_termination(action):
    pool, cancel = Controlled("hang"), threading.Event()
    with ThreadPoolExecutor(max_workers=1) as threads:
        future = threads.submit(pool.validate, RAW, cancel=cancel)
        try:
            assert pool.spawned.wait(5)
            if action == "cancel":
                cancel.set()
            elif action == "terminate":
                pool.processes[-1].terminate()
            else:
                pool.close()
            clean_local(future.result(timeout=5))
        finally:
            cancel.set()
            pool.close()


def test_concurrency_saturation_and_recovery():
    pools = [Controlled("hang", max_workers=2) for _ in range(3)]
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=2) as threads:
        jobs = [threads.submit(p.validate, RAW, cancel=cancel) for p in pools[:2]]
        try:
            assert all(p.spawned.wait(5) for p in pools[:2])
            for _ in range(10):
                assert pools[2].validate(RAW).reason == "saturated"
            assert not pools[2].processes
        finally:
            cancel.set()
            for job in jobs:
                clean_local(job.result(timeout=5))
            for pool in pools:
                pool.close()
    with isolated.IsolatedDecoder() as pool:
        assert pool.validate(RAW).status == isolated.Status.VALID


def test_repeated_recovery_and_no_retries():
    with Controlled("crash") as pool:
        for _ in range(3):
            clean_local(pool.validate(RAW))
        pool._command = lambda: isolated.IsolatedDecoder._command(pool)
        assert pool.validate(RAW).status == isolated.Status.VALID
        assert len(pool.processes) == 4
        assert all(p.returncode is not None and p.stdin.closed and p.stdout.closed for p in pool.processes)
    assert not [t for t in threading.enumerate() if t.name.startswith("decoder-ipc-")]


def test_cleanup_uncertainty_quarantines_capacity(monkeypatch):
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(isolated, "_GLOBAL_SLOTS", slots)
    with isolated.IsolatedDecoder() as pool:
        spawn = pool._spawn
        def bad_accounting():
            process = spawn()
            def unavailable():
                raise OSError("controlled post-reap accounting failure")
            process.metrics = unavailable
            return process
        monkeypatch.setattr(pool, "_spawn", bad_accounting)
        result = pool.validate(RAW)
        assert result.reason == "cleanup_failure" and not result.metrics["reaped"]
        assert pool.validate(RAW).reason == "saturated"
        assert not slots.acquire(blocking=False)


def test_parent_death_kills_confined_worker():
    # Adopt/reap the orphan in the harness rather than depending on WSL PID 1
    # to reap promptly. This is a test supervisor, not a node-wide setting.
    libc, previous = C.CDLL(None), C.c_int()
    assert libc.prctl(37, C.byref(previous), 0, 0, 0) == 0  # GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    with Controlled("controller") as template:
        parent = subprocess.Popen(template._command(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pid = None
    try:
        with ThreadPoolExecutor(max_workers=1) as reader:
            line = reader.submit(parent.stdout.readline)
            try:
                pid = int(line.result(timeout=8))
            except BaseException:
                parent.kill()
                raise
        parent.kill()
        parent.wait(timeout=3)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            reaped, status = os.waitpid(pid, os.WNOHANG)
            if reaped:
                assert os.waitstatus_to_exitcode(status) == -signal.SIGKILL
                assert not Path(f"/proc/{pid}").exists()
                pid = None
                break
            time.sleep(0.01)
        else:
            pytest.fail("orphaned live worker")
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        parent.stdout.close()
        if pid is not None:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def test_bootstrap_parent_race_exits_before_ready():
    with isolated.IsolatedDecoder() as pool:
        command = pool._command()
    command[4] = "2147483647"  # Safely nonexistent expected parent.
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    assert process.returncode == 72 and not process.stdout


def test_bootstrap_dead_creator_thread_exits_before_ready():
    with isolated.IsolatedDecoder() as pool:
        command = pool._command()
    command[-1] = "2147483647"
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    assert process.returncode == 72 and not process.stdout


def test_oversized_request_is_rejected_in_confined_worker():
    with isolated.IsolatedDecoder() as pool:
        process = pool._spawn()
        try:
            assert ipc.read_message(process.stdout, 0) == (dict(v=1, kind="ready"), b"")
            process.stdin.write(ipc.PREFIX.pack(ipc.MAGIC, 1, ipc.MAX_REQUEST + 1))
            process.stdin.close()
            assert process.wait(3) != 0
        finally:
            process.close()
