"""Fixed, non-destructive Linux fault probes; never an API command override."""
import ctypes as C
import errno
import hashlib
import importlib.util
import os
from pathlib import Path
import resource
import socket
import subprocess
import sys
import sysconfig
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from codec_prototype import worker_ipc as ipc
from codec_prototype.worker_linux import prepare, confine, IsolationUnavailable


def command(limits, mode):
    return [sys.executable, "-I", "-u", __file__, str(os.getpid()),
            str(limits.memory_bytes), str(limits.cpu_seconds), sysconfig.get_path("purelib"), mode,
            str(threading.get_native_id())]


def main():
    parent, memory, cpu, site, mode, parent_tid = sys.argv[1:]
    sys.path.insert(0, site)
    if mode == "controller":
        from codec_prototype.isolated_decoder import IsolatedDecoder, Limits
        class Controller(IsolatedDecoder):
            def _command(self):
                return command(self.limits, "hang")
            def _spawn(self):
                process = super()._spawn()
                # Wait for actual confined READY, without consuming the pipe.
                # The controller's coordinator publishes PID when the worker
                # is observed to have loaded its filter in /proc status.
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    status = Path(f"/proc/{process.pid}/status").read_text()
                    if "NoNewPrivs:\t1" in status and "Seccomp:\t2" in status:
                        print(process.pid, flush=True)
                        return process
                    time.sleep(0.01)
                process.terminate()
                process.wait(2)
                process.close()
                raise OSError("controller readiness")
        with Controller(limits=Limits(wall_seconds=60)) as pool:
            pool.validate(ipc.canonical(dict(encoding_version=1, codec_id="identity", codec_version=1,
                original_size=3, stored_size=3, mime_type="image/png",
                original_sha256=hashlib.sha256(b"abc").hexdigest(), payload="YWJj")))
        return
    prepare(int(parent), int(memory), float(cpu), int(parent_tid))
    from codec_prototype import strict_decoder as codec
    codec._backend()
    spec = importlib.util.spec_from_file_location("fixed_fault_fixture", ROOT / "tests/helpers/decoder_worker_fixture.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    libc = C.CDLL(None, use_errno=True)
    original_uid = os.getuid()
    # All objects/imports needed by probes exist before the filter is sealed.
    secret = str(ROOT / "docs/milestone-7-codec-security-contract.md")
    if mode == "missing_seccomp":
        load = C.CDLL
        def unavailable(name, *args, **kwargs):
            if name == "libseccomp.so.2":
                raise OSError("controlled missing mandatory library")
            return load(name, *args, **kwargs)
        C.CDLL = unavailable
    confine()
    if mode not in ("filesystem", "network", "spawn_child", "privilege", "descriptors", "limits", "allocate_native"):
        sys.argv = [fixture.__file__, site, mode]
        fixture.main()
        return
    source, target = sys.stdin.buffer, sys.stdout.buffer
    ipc.write_message(target, dict(v=1, kind="ready"))
    request, raw = ipc.read_message(source, ipc.MAX_REQUEST)
    ipc.request_identity(request)
    assert hashlib.sha256(raw).hexdigest() == request["request_sha256"] and not source.read(1)
    def denied(action):
        try:
            action()
        except OSError as exc:
            assert exc.errno == errno.EPERM, exc
        else:
            raise AssertionError("restriction absent")
    if mode == "filesystem":
        denied(lambda: os.open(secret, os.O_RDONLY))
        denied(lambda: os.open(secret, os.O_WRONLY))
        reason = "filesystem_denied"
    elif mode == "network":
        for family, kind in ((socket.AF_INET, socket.SOCK_STREAM), (socket.AF_INET6, socket.SOCK_DGRAM),
                             (socket.AF_UNIX, socket.SOCK_STREAM)):
            denied(lambda: socket.socket(family, kind))
        reason = "network_denied"
    elif mode == "spawn_child":
        denied(lambda: subprocess.Popen([sys.executable, "-I", "-c", "pass"]))
        # Direct fork/exec are denied too, independently of Python's launcher.
        assert libc.fork() == -1 and C.get_errno() == errno.EPERM
        assert libc.execve(C.c_char_p(b"/nonexistent-safe-probe"), None, None) == -1
        assert C.get_errno() == errno.EPERM
        reason = "child_denied"
    elif mode == "privilege":
        assert libc.setuid(original_uid) == -1 and C.get_errno() == errno.EPERM
        assert libc.prctl(4, 1, 0, 0, 0) == -1 and C.get_errno() == errno.EPERM
        reason = "privilege_denied"
    elif mode == "descriptors":
        for fd in range(3, 16):
            try:
                os.fstat(fd)
            except OSError as exc:
                assert exc.errno == errno.EBADF
            else:
                raise AssertionError("ambient descriptor")
        reason = "descriptors_closed"
    elif mode == "allocate_native":
        libc.mmap.argtypes = [C.c_void_p, C.c_size_t, C.c_int, C.c_int, C.c_int, C.c_long]
        libc.mmap.restype = C.c_void_p
        address = libc.mmap(None, 96 * 1024**2, 3, 0x22, -1, 0)
        assert address == C.c_void_p(-1).value and C.get_errno() == errno.ENOMEM
        reason = "native_memory_denied"
    else:
        # Querying prlimit/getrlimit is deliberately forbidden after sealing.
        reason = "limits_sealed"
        class Rlimit(C.Structure):
            _fields_ = [("soft", C.c_ulong), ("hard", C.c_ulong)]
        config = Rlimit(2**40, 2**40)
        assert libc.setrlimit(resource.RLIMIT_AS, C.byref(config)) == -1
        assert C.get_errno() == errno.EPERM
    ipc.write_message(target, ipc.result_header(request, "INDETERMINATE_LOCAL_FAILURE", reason=reason))


if __name__ == "__main__":
    try:
        main()
    except IsolationUnavailable as exc:
        ipc.write_message(sys.stdout.buffer, dict(v=1, kind="unavailable", reason=exc.reason))
