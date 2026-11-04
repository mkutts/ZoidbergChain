"""Linux-only offline worker containment; no root or preexec_fn required.

Trusted bootstrap runs before READY. Untrusted bytes enter only after the
mandatory seccomp allowlist, hard rlimits and parent-death setup succeed.
"""
from __future__ import annotations

import ctypes as C
import errno
import math
import os
import platform
import signal
import subprocess
import sys
import threading
import time


class IsolationUnavailable(OSError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class CleanupFailure(OSError):
    cleanup_uncertain = True


def _prctl(libc, operation, value=0):
    # prctl is variadic: explicitly size all arguments, including zeroes.
    if libc.prctl(C.c_int(operation), C.c_ulong(value), C.c_ulong(0), C.c_ulong(0), C.c_ulong(0)) != 0:
        raise IsolationUnavailable("linux_prctl_unavailable")


def prepare(parent_pid, memory_bytes, cpu_seconds, parent_tid):
    """Trusted child only, before native backend imports or any request read."""
    import resource
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise IsolationUnavailable("linux_architecture_unsupported")
    libc = C.CDLL(None, use_errno=True)
    _prctl(libc, 1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    if os.getppid() != parent_pid or not os.path.exists(f"/proc/{parent_pid}/task/{parent_tid}"):
        os._exit(72)  # Parent died before PDEATHSIG was armed.
    if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
        raise IsolationUnavailable("linux_session_unavailable")
    if os.getuid() == 0 or os.geteuid() != os.getuid() or os.getegid() != os.getgid():
        raise IsolationUnavailable("linux_privileged_identity")
    # Empty all capability sets; root and set-ID runtimes are refused above.
    class CapHeader(C.Structure):
        _fields_ = [("version", C.c_uint32), ("pid", C.c_int)]
    class CapData(C.Structure):
        _fields_ = [("effective", C.c_uint32), ("permitted", C.c_uint32), ("inheritable", C.c_uint32)]
    header, data = CapHeader(0x20080522, 0), (CapData * 2)()
    if libc.capset(C.byref(header), C.byref(data)) != 0:
        raise IsolationUnavailable("linux_capabilities_unavailable")
    _prctl(libc, 4, 0)  # PR_SET_DUMPABLE: deny same-UID ptrace/proc memory access.
    _prctl(libc, 38, 1)  # PR_SET_NO_NEW_PRIVS, irrevocable.
    if libc.prctl(C.c_int(39), C.c_ulong(0), C.c_ulong(0), C.c_ulong(0), C.c_ulong(0)) != 1:
        raise IsolationUnavailable("linux_no_new_privs_unavailable")
    if libc.capget(C.byref(header), C.byref(data)) != 0 or any(
            part.effective or part.permitted or part.inheritable for part in data):
        raise IsolationUnavailable("linux_capabilities_unavailable")
    try:
        settings = ((resource.RLIMIT_AS, memory_bytes),
                    (resource.RLIMIT_CPU, math.ceil(cpu_seconds)),
                    (resource.RLIMIT_NPROC, 1), (resource.RLIMIT_NOFILE, 16),
                    (resource.RLIMIT_CORE, 0), (resource.RLIMIT_FSIZE, 0),
                    (resource.RLIMIT_MEMLOCK, 0))
        for kind, budget in settings:
            _, inherited = resource.getrlimit(kind)
            bound = budget if inherited == resource.RLIM_INFINITY else min(budget, inherited)
            resource.setrlimit(kind, (bound, bound))
            if resource.getrlimit(kind) != (bound, bound):
                raise OSError("rlimit readback")
        allowed = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(allowed)})
        if len(os.sched_getaffinity(0)) != 1:
            raise OSError("affinity readback")
    except (OSError, ValueError) as exc:
        raise IsolationUnavailable("linux_resource_controls_unavailable") from exc


# No open/openat, sockets, clone/fork/exec, signals to other processes, ptrace,
# credential/namespace changes, io_uring, bpf, descriptor duplication or prlimit.
# Unknown syscalls are denied as well. libseccomp validates the native ABI and
# kills a call using an unconfigured architecture; no raw syscall-number table.
ALLOWED_SYSCALLS = (
    "brk", "mmap", "munmap", "mremap", "mprotect", "madvise",
    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "sigaltstack",
    "futex", "clock_gettime", "clock_nanosleep", "nanosleep", "restart_syscall",
    "getpid", "getppid", "gettid", "getrandom", "sched_yield", "getrusage",
    "close", "fstat", "exit", "exit_group",
)


def confine():
    """Install default-deny seccomp after all trusted imports; before READY."""
    try:
        # /proc is needed only during trusted bootstrap. Do not retain any
        # library-opened file, directory, socket or other ambient descriptor.
        if len(os.listdir("/proc/self/task")) != 1:
            raise IsolationUnavailable("linux_bootstrap_threads")
        for entry in os.listdir("/proc/self/fd"):
            fd = int(entry)
            if fd > 2:
                try:
                    os.close(fd)
                except OSError as exc:
                    if exc.errno != errno.EBADF:
                        raise
        sec = C.CDLL("libseccomp.so.2", use_errno=True)
        sec.seccomp_init.argtypes, sec.seccomp_init.restype = [C.c_uint32], C.c_void_p
        sec.seccomp_release.argtypes = [C.c_void_p]
        sec.seccomp_load.argtypes = [C.c_void_p]
        sec.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
        class Arg(C.Structure):
            _fields_ = [("arg", C.c_uint), ("op", C.c_int), ("a", C.c_uint64), ("b", C.c_uint64)]
        sec.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint, C.POINTER(Arg)]
        ctx = sec.seccomp_init(0x00050000 | errno.EPERM)  # SCMP_ACT_ERRNO
        if not ctx:
            raise OSError("seccomp_init")
        try:
            def allow(name, fd=None):
                number = sec.seccomp_syscall_resolve_name(name.encode("ascii"))
                arg = Arg(0, 4, fd, 0) if fd is not None else None  # SCMP_CMP_EQ
                if number < 0 or sec.seccomp_rule_add_array(ctx, 0x7fff0000, number,
                        int(arg is not None), C.byref(arg) if arg is not None else None) != 0:
                    raise OSError("seccomp_rule")
            for name in ALLOWED_SYSCALLS:
                allow(name)
            allow("read", 0)
            allow("write", 1)
            allow("write", 2)
            if sec.seccomp_load(ctx) != 0:
                raise OSError("seccomp_load")
        finally:
            sec.seccomp_release(ctx)
    except IsolationUnavailable:
        raise
    except (OSError, ValueError, MemoryError, AttributeError) as exc:
        raise IsolationUnavailable("linux_seccomp_unavailable") from exc


class LinuxProcess:
    """Coordinator-side adapter. Never fork Python with a preexec callback."""
    def __init__(self, command, limits, cwd):
        self.limits, self.usage = limits, None
        self._lock = threading.RLock()
        self.returncode = None
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, close_fds=True, start_new_session=True,
            cwd=str(cwd), env={"LANG": "C", "LC_ALL": "C"})
        self.pid = self.process.pid
        self.stdin, self.stdout = self.process.stdin, self.process.stdout

    def poll(self):
        # wait4 captures per-child native RSS/CPU, unlike RUSAGE_CHILDREN deltas
        # which mix simultaneous workers. Popen must not reap independently.
        with self._lock:
            if self.returncode is None:
                pid, status, usage = os.wait4(self.pid, os.WNOHANG)
                if pid:
                    self.returncode = os.waitstatus_to_exitcode(status)
                    self.process.returncode, self.usage = self.returncode, usage
            return self.returncode

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("worker reap")
            time.sleep(0.005)
        return self.returncode

    def terminate(self):
        # Signal the group while its leader PID is still owned/unreaped. No
        # post-reap killpg that might target a recycled process/group ID.
        with self._lock:
            if self.returncode is None:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def user_cpu_ns(self):
        # Interface name retained for Windows. Linux budgets TOTAL process CPU.
        if self.returncode is not None:
            return int((self.usage.ru_utime + self.usage.ru_stime) * 1e9)
        try:
            with open(f"/proc/{self.pid}/stat", encoding="ascii") as stream:
                fields = stream.read(4096).rsplit(")", 1)[1].split()
            return int((int(fields[11]) + int(fields[12])) * 1e9 / os.sysconf("SC_CLK_TCK"))
        except FileNotFoundError:
            if self.poll() is not None:
                return self.user_cpu_ns()
            raise

    def metrics(self):
        if self.usage is None:
            raise OSError("worker not reaped")
        return dict(peak_rss_bytes=self.usage.ru_maxrss * 1024,
                    process_user_ns=int(self.usage.ru_utime * 1e9),
                    process_kernel_ns=int(self.usage.ru_stime * 1e9),
                    configured_address_space_bytes=self.limits.memory_bytes,
                    configured_total_cpu_ns=int(self.limits.cpu_seconds * 1e9),
                    kernel_cpu_seconds=math.ceil(self.limits.cpu_seconds))

    def close(self):
        errors = []
        if self.returncode is None:
            try:
                self.terminate()
                self.wait(2)
            except (OSError, TimeoutError) as exc:
                errors.append(exc)
        for stream in (self.stdin, self.stdout):
            try:
                stream.close()
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise CleanupFailure("Linux worker cleanup could not be verified") from errors[0]
