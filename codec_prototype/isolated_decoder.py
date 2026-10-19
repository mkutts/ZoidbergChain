"""Offline, bounded per-request decoder processes. No production integration.

Only the child calls decode(). Operational failures never imply INVALID.
Windows resource controls are required; other platforms fail closed locally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

from . import strict_decoder as codec
from . import worker_ipc as ipc

GLOBAL_CONCURRENCY = 2
_GLOBAL_SLOTS = threading.BoundedSemaphore(GLOBAL_CONCURRENCY)
ROOT = Path(__file__).resolve().parents[1]


class Status(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    INDETERMINATE_LOCAL_FAILURE = "INDETERMINATE_LOCAL_FAILURE"


@dataclass(frozen=True)
class Limits:
    memory_bytes: int = 128 * 1024 * 1024
    cpu_seconds: float = 5.0  # Windows user-mode CPU, not total/kernel time.
    wall_seconds: float = 10.0  # Begins at READY; never a validity predicate.
    startup_seconds: float = 5.0

    def __post_init__(self):
        if type(self.memory_bytes) is not int or not 16 * 1024**2 <= self.memory_bytes <= 256 * 1024**2:
            raise ValueError("memory_bytes must be 16..256 MiB")
        for name, maximum in (("cpu_seconds", 30), ("wall_seconds", 60), ("startup_seconds", 15)):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0.1 <= value <= maximum:
                raise ValueError(f"invalid operational {name}")


@dataclass(frozen=True)
class Outcome:
    status: Status
    original: bytes | None = None
    stage: str | None = None
    code: str | None = None
    reason: str | None = None
    metrics: dict = field(default_factory=dict)


def local(reason, metrics=None):
    return Outcome(Status.INDETERMINATE_LOCAL_FAILURE, reason=reason, metrics=metrics if metrics is not None else {})


class IsolatedDecoder:
    """Synchronous API; use caller threads for up to max_workers simultaneous jobs.

    There is no waiting-job queue, automatic retry, persistent worker, or public
    worker-command override. All instances share the two-slot process budget.
    Call close(), preferably via a context manager, to cancel outstanding calls.
    """
    def __init__(self, *, max_workers=1, limits=None):
        if type(max_workers) is not int or not 1 <= max_workers <= GLOBAL_CONCURRENCY:
            raise ValueError("max_workers must be 1 or 2")
        self.limits = limits or Limits()
        if not isinstance(self.limits, Limits):
            raise TypeError("limits")
        self._slots = threading.BoundedSemaphore(max_workers)
        self._lock = threading.Lock()
        self._active = {}
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        with self._lock:
            self._closed = True
            active = list(self._active.items())
            for cancel, _ in active:
                cancel.set()
        deadline = time.monotonic() + 5
        for _, done in active:
            if not done.wait(max(0, deadline - time.monotonic())):
                raise TimeoutError("decoder shutdown did not finish; capacity remains reserved")

    def _command(self):
        # The Windows venv redirector itself creates another process. Launch
        # the base interpreter directly and provide only the trusted venv site.
        return [str(Path(sys._base_executable).resolve()), "-I", "-u",
                str(ROOT / "codec_prototype/worker_entry.py"),
                str(Path(sys.prefix) / "Lib/site-packages")]

    def _spawn(self):
        if os.name != "nt":
            raise NotImplementedError("OS resource enforcement is not tested on this platform")
        from .worker_windows import WindowsProcess
        return WindowsProcess(self._command(), self.limits, ROOT)

    def validate(self, raw: bytes, *, cancel=None):
        started = time.perf_counter_ns()
        own_cancel, completed = threading.Event(), threading.Event()
        with self._lock:
            if self._closed:
                return local("closed")
            if not self._slots.acquire(blocking=False):
                return local("saturated")
            if not _GLOBAL_SLOTS.acquire(blocking=False):
                self._slots.release()
                return local("saturated")
            self._active[own_cancel] = completed
        process = exchange = None
        reusable = True
        metrics = {}
        outcome = local("internal_error", metrics)
        try:
            if own_cancel.is_set() or (cancel is not None and cancel.is_set()):
                return local("cancelled")
            # Descriptor parsing is bounded and does not reconstruct E or M.
            # Its exact existing deterministic errors are safe to return here.
            try:
                desc = codec.parse_descriptor(raw)
            except codec.CodecReject as exc:
                return Outcome(Status.INVALID, stage=exc.stage, code=exc.code)
            if own_cancel.is_set() or (cancel is not None and cancel.is_set()):
                return local("cancelled")
            if os.name != "nt":
                return local("unsupported_platform")
            request = dict(v=1, kind="request", id=uuid.uuid4().hex,
                           request_sha256=hashlib.sha256(raw).hexdigest())
            expected_size = desc.get("original_size") if type(desc) is dict else None
            output_cap = expected_size if type(expected_size) is int and 1 <= expected_size <= ipc.MAX_OUTPUT else 0
            launch = time.perf_counter_ns()
            process = self._spawn()
            metrics["pid"] = process.pid
            finished, ready = threading.Event(), threading.Event()
            state = {}

            def communicate():
                try:
                    meta, body = ipc.read_message(process.stdout, 0)
                    if meta != dict(v=1, kind="ready") or type(meta["v"]) is not int or body:
                        raise ipc.IPCError("ready")
                    state["ready_at"] = time.perf_counter_ns()
                    ready.set()
                    ipc.write_message(process.stdin, request, raw, ipc.MAX_REQUEST)
                    process.stdin.close()  # Exactly one request; worker checks EOF.
                    meta, body = ipc.read_message(process.stdout, output_cap)
                    if process.stdout.read(1):
                        raise ipc.IPCError("trailing_response")
                    state["response"] = (meta, body)
                except Exception:
                    state["error"] = "ipc_failure"
                finally:
                    state["exchange_end"] = time.perf_counter_ns()
                    finished.set()

            exchange = threading.Thread(target=communicate, name=f"decoder-ipc-{process.pid}", daemon=True)
            exchange.start()
            while True:
                if own_cancel.is_set() or (cancel is not None and cancel.is_set()):
                    outcome = local("cancelled", metrics)
                    break
                # Windows checks native job CPU limits periodically and can
                # substantially overshoot short budgets. Sample user CPU too;
                # this remains an operational failure, never protocol INVALID.
                if process.user_cpu_ns() >= self.limits.cpu_seconds * 1e9:
                    outcome = local("cpu_limit", metrics)
                    break
                now = time.perf_counter_ns()
                if ready.is_set():
                    if now - state["ready_at"] > self.limits.wall_seconds * 1e9:
                        outcome = local("timeout", metrics)
                        break
                elif now - launch > self.limits.startup_seconds * 1e9:
                    outcome = local("startup_timeout", metrics)
                    break
                if finished.wait(0.01):
                    if "error" in state:
                        outcome = local("worker_crash_or_ipc", metrics)
                        break
                    # Even a complete success message requires a clean exit.
                    if process.poll() is None:
                        own_cancel.wait(0.01)
                        continue
                    if process.poll() != 0:
                        outcome = local("worker_exit", metrics)
                    else:
                        try:
                            outcome = self._response(request, desc, *state["response"], metrics)
                        except (ipc.IPCError, KeyError, TypeError, ValueError):
                            outcome = local("malformed_response", metrics)
                    break
            if ready.is_set():
                metrics["startup_ns"] = state["ready_at"] - launch
                metrics["exchange_ns"] = state.get("exchange_end", time.perf_counter_ns()) - state["ready_at"]
        except (OSError, NotImplementedError) as exc:
            if getattr(exc, "cleanup_uncertain", False):
                reusable = False
            outcome = local("startup_or_control_failure", metrics)
        except MemoryError:
            outcome = local("parent_allocation_failure", metrics)
        finally:
            cleanup_start = time.perf_counter_ns()
            if process is not None:
                try:
                    if process.poll() is None:
                        process.terminate()
                    metrics["exit_code"] = process.wait(2)
                    metrics.update(process.metrics())
                except (OSError, TimeoutError):
                    reusable = False
                    outcome = local("cleanup_failure", metrics)
                finally:
                    try:
                        process.close()
                    except OSError:
                        reusable = False
                        outcome = local("cleanup_failure", metrics)
                if exchange is not None:
                    exchange.join(2)
                    if exchange.is_alive():
                        reusable = False
                        outcome = local("cleanup_failure", metrics)
                metrics["reaped"] = reusable
            metrics["cleanup_ns"] = time.perf_counter_ns() - cleanup_start
            metrics["total_ns"] = time.perf_counter_ns() - started
            with self._lock:
                # Fail closed on unproven cleanup: never recycle capacity and
                # thereby permit an unbounded accumulation of processes/threads.
                if reusable:
                    self._slots.release()
                    _GLOBAL_SLOTS.release()
                self._active.pop(own_cancel)
                completed.set()
        return outcome

    @staticmethod
    def _response(request, descriptor, meta, body, metrics):
        common = {"v", "kind", "id", "request_sha256", "status"}
        if (type(meta.get("v")) is not int or meta["v"] != 1 or meta.get("kind") != "result"
                or meta.get("id") != request["id"] or meta.get("request_sha256") != request["request_sha256"]):
            raise ipc.IPCError("identity")
        status = meta.get("status")
        if status == "VALID":
            if set(meta) != common | {"size", "sha256", "parse_ns", "decode_ns"}:
                raise ipc.IPCError("valid_fields")
            if (type(meta["size"]) is not int or not 1 <= meta["size"] <= ipc.MAX_OUTPUT
                    or meta["size"] != len(body) or type(descriptor) is not dict
                    or type(descriptor.get("original_size")) is not int
                    or len(body) != descriptor["original_size"]
                    or type(meta["sha256"]) is not str or not ipc.DIGEST.fullmatch(meta["sha256"])
                    or meta["sha256"] != descriptor.get("original_sha256")
                    or hashlib.sha256(body).hexdigest() != meta["sha256"]):
                raise ipc.IPCError("output_identity")
            for name in ("parse_ns", "decode_ns"):
                if type(meta[name]) is not int or not 0 <= meta[name] <= 10**15:
                    raise ipc.IPCError("timing_metadata")
                metrics["worker_" + name] = meta[name]
            return Outcome(Status.VALID, original=body, metrics=metrics)
        if status == "INVALID":
            if (set(meta) != common | {"stage", "code"} or body
                    or meta["stage"] not in ("descriptor", "frame", "decode", "integrity")
                    or type(meta["code"]) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", meta["code"])):
                raise ipc.IPCError("invalid_fields")
            return Outcome(Status.INVALID, stage=meta["stage"], code=meta["code"], metrics=metrics)
        if status == "INDETERMINATE_LOCAL_FAILURE":
            if (set(meta) != common | {"reason"} or body or type(meta["reason"]) is not str
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", meta["reason"])):
                raise ipc.IPCError("local_fields")
            return local("worker_" + meta["reason"], metrics)
        raise ipc.IPCError("status")
