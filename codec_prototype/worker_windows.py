"""Windows-only Job Object resource containment, NOT a privilege sandbox.

Atomic JOB_LIST assignment at CreateProcess prevents a launch/assignment orphan
gap. The child never owns the job handle; closing it kills every job member.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import subprocess
import threading

SIZE = C.c_size_t
U64 = C.c_ulonglong


class BasicLimits(C.Structure):
    _fields_ = [("process_time", C.c_longlong), ("job_time", C.c_longlong), ("flags", W.DWORD),
                ("min_ws", SIZE), ("max_ws", SIZE), ("active", W.DWORD),
                ("affinity", SIZE), ("priority", W.DWORD), ("scheduling", W.DWORD)]


class IOCounters(C.Structure):
    _fields_ = [(name, U64) for name in ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(C.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IOCounters), ("process_memory", SIZE),
                ("job_memory", SIZE), ("peak_process_memory", SIZE), ("peak_job_memory", SIZE)]


class StartupInfo(C.Structure):
    _fields_ = [("cb", W.DWORD), ("reserved", W.LPWSTR), ("desktop", W.LPWSTR), ("title", W.LPWSTR),
                *[(name, W.DWORD) for name in ("x", "y", "xsize", "ysize", "xchars", "ychars", "fill", "flags")],
                ("show", W.WORD), ("reserved_size", W.WORD), ("reserved_bytes", C.c_void_p),
                ("stdin", W.HANDLE), ("stdout", W.HANDLE), ("stderr", W.HANDLE)]


class StartupInfoEx(C.Structure):
    _fields_ = [("startup", StartupInfo), ("attributes", C.c_void_p)]


class ProcessInfo(C.Structure):
    _fields_ = [("process", W.HANDLE), ("thread", W.HANDLE), ("pid", W.DWORD), ("tid", W.DWORD)]


class MemoryCounters(C.Structure):
    _fields_ = [("cb", W.DWORD), ("faults", W.DWORD),
                *[(name, SIZE) for name in ("peak_ws", "ws", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]]


_launch_lock = threading.Lock()


class CleanupFailure(OSError):
    cleanup_uncertain = True


class WindowsProcess:
    def __init__(self, command, limits, cwd):
        if os.name != "nt":
            raise OSError("Windows Job Object enforcement unavailable")
        import msvcrt
        self.k = C.WinDLL("kernel32", use_last_error=True)
        def bind(name, restype, args):
            fn = getattr(self.k, name)
            fn.restype, fn.argtypes = restype, args
            return fn
        self._close = bind("CloseHandle", W.BOOL, [W.HANDLE])
        self._wait = bind("WaitForSingleObject", W.DWORD, [W.HANDLE, W.DWORD])
        self._exit = bind("GetExitCodeProcess", W.BOOL, [W.HANDLE, C.POINTER(W.DWORD)])
        self._query = bind("QueryInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p])
        self._kill = bind("TerminateJobObject", W.BOOL, [W.HANDLE, W.UINT])
        self._times = bind("GetProcessTimes", W.BOOL, [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4)
        create_job = bind("CreateJobObjectW", W.HANDLE, [C.c_void_p, W.LPCWSTR])
        set_job = bind("SetInformationJobObject", W.BOOL, [W.HANDLE, C.c_int, C.c_void_p, W.DWORD])
        init = bind("InitializeProcThreadAttributeList", W.BOOL, [C.c_void_p, W.DWORD, W.DWORD, C.POINTER(SIZE)])
        update = bind("UpdateProcThreadAttribute", W.BOOL, [C.c_void_p, W.DWORD, SIZE, C.c_void_p, SIZE, C.c_void_p, C.c_void_p])
        delete = bind("DeleteProcThreadAttributeList", None, [C.c_void_p])
        create = bind("CreateProcessW", W.BOOL, [W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p,
                      W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(StartupInfoEx), C.POINTER(ProcessInfo)])
        self.job, self.handle = None, None
        self.stdin = self.stdout = None
        self.pid = None
        fds = []
        attributes_ready = False
        try:
            self.job = create_job(None, None)
            self.check(self.job)
            config = ExtendedLimits()
            # PROCESS_TIME | ACTIVE_PROCESS | PROCESS_MEMORY | JOB_MEMORY |
            # AFFINITY | KILL_ON_JOB_CLOSE. Neither breakaway flag is allowed.
            config.basic.flags = 0x2 | 0x8 | 0x100 | 0x200 | 0x10 | 0x2000
            config.basic.process_time = int(limits.cpu_seconds * 10_000_000)
            config.basic.active = 1
            affinity = bind("GetProcessAffinityMask", W.BOOL, [W.HANDLE, C.POINTER(SIZE), C.POINTER(SIZE)])
            current = bind("GetCurrentProcess", W.HANDLE, [])
            mask, system = SIZE(), SIZE()
            self.check(affinity(current(), C.byref(mask), C.byref(system)))
            config.basic.affinity = mask.value & -mask.value  # One allowed CPU.
            config.process_memory = config.job_memory = limits.memory_bytes
            self.check(set_job(self.job, 9, C.byref(config), C.sizeof(config)))
            child_in, parent_in = os.pipe()
            fds.extend((child_in, parent_in))
            parent_out, child_out = os.pipe()
            fds.extend((parent_out, child_out))
            null_fd = os.open(os.devnull, os.O_WRONLY)
            fds.append(null_fd)
            inherited = (W.HANDLE * 3)(*[msvcrt.get_osfhandle(fd) for fd in (child_in, child_out, null_fd)])
            jobs = (W.HANDLE * 1)(self.job)
            needed = SIZE()
            init(None, 2, 0, C.byref(needed))
            if not needed.value:
                raise C.WinError(C.get_last_error())
            attributes = C.create_string_buffer(needed.value)
            self.check(init(attributes, 2, 0, C.byref(needed)))
            attributes_ready = True
            self.check(update(attributes, 0, 0x20002, inherited, C.sizeof(inherited), None, None))
            self.check(update(attributes, 0, 0x2000D, jobs, C.sizeof(jobs), None, None))
            si = StartupInfoEx()
            si.startup.cb = C.sizeof(si)
            si.startup.flags = 0x100  # STARTF_USESTDHANDLES
            si.startup.stdin, si.startup.stdout, si.startup.stderr = inherited
            si.attributes = C.cast(attributes, C.c_void_p)
            pi = ProcessInfo()
            environment = {k: os.environ[k] for k in ("SystemRoot", "WINDIR", "TEMP", "TMP") if k in os.environ}
            env = C.create_unicode_buffer("\0".join(f"{k}={v}" for k, v in sorted(environment.items())) + "\0\0")
            # Serialize our inheritable-handle window. HANDLE_LIST restricts
            # this child; unrelated code using broad inheritance remains a host
            # integration concern. No job/process handle is inherited.
            with _launch_lock:
                for fd in (child_in, child_out, null_fd):
                    os.set_inheritable(fd, True)
                try:
                    self.check(create(command[0], C.create_unicode_buffer(subprocess.list2cmdline(command)),
                                      None, None, True, 0x80000 | 0x8000000 | 0x400,
                                      C.cast(env, C.c_void_p), str(cwd), C.byref(si), C.byref(pi)))
                    self.handle, self.pid = pi.process, pi.pid
                    self._close(pi.thread)
                finally:
                    for fd in (child_in, child_out, null_fd):
                        os.set_inheritable(fd, False)
            for fd in (child_in, child_out, null_fd):
                os.close(fd)
                fds.remove(fd)
            self.stdin = os.fdopen(parent_in, "wb", buffering=0)
            fds.remove(parent_in)
            self.stdout = os.fdopen(parent_out, "rb", buffering=0)
            fds.remove(parent_out)
        except BaseException:
            certain = True
            if self.handle:
                try:
                    if self.poll() is None:
                        self.terminate()
                    self.wait(2)
                except (OSError, TimeoutError):
                    certain = False
            try:
                self.close()
            except OSError:
                certain = False
            if not certain:
                raise CleanupFailure("startup cleanup could not be verified") from None
            raise
        finally:
            if attributes_ready:
                delete(attributes)
            for fd in fds:
                os.close(fd)

    @staticmethod
    def check(ok):
        if not ok:
            raise C.WinError(C.get_last_error())

    def poll(self):
        state = self._wait(self.handle, 0)
        if state == 258:
            return None
        if state != 0:
            raise C.WinError(C.get_last_error())
        code = W.DWORD()
        self.check(self._exit(self.handle, C.byref(code)))
        return code.value

    def wait(self, seconds):
        state = self._wait(self.handle, max(0, int(seconds * 1000)))
        if state == 258:
            raise TimeoutError("worker reap")
        if state != 0:
            raise C.WinError(C.get_last_error())
        return self.poll()

    def terminate(self):
        self.check(self._kill(self.job, 71))

    def user_cpu_ns(self):
        stamps = [W.FILETIME() for _ in range(4)]
        self.check(self._times(self.handle, *[C.byref(t) for t in stamps]))
        user = stamps[3]
        return ((user.dwHighDateTime << 32) | user.dwLowDateTime) * 100

    def metrics(self):
        info = ExtendedLimits()
        self.check(self._query(self.job, 9, C.byref(info), C.sizeof(info), None))
        stamps = [W.FILETIME() for _ in range(4)]
        self.check(self._times(self.handle, *[C.byref(t) for t in stamps]))
        def ns(stamp):
            return ((stamp.dwHighDateTime << 32) | stamp.dwLowDateTime) * 100
        return dict(peak_job_commit_bytes=info.peak_job_memory,
                    peak_process_commit_bytes=info.peak_process_memory,
                    process_user_ns=ns(stamps[3]), process_kernel_ns=ns(stamps[2]),
                    enforced_memory_bytes=info.job_memory, enforced_active_processes=info.basic.active,
                    enforced_user_cpu_ns=info.basic.process_time * 100,
                    enforced_affinity=info.basic.affinity, enforced_flags=info.basic.flags)

    def close(self):
        # The non-inherited job handle is closed first: process death also
        # releases blocked IPC operations. Callers explicitly reap before here.
        errors = []
        if self.job:
            if not self._close(self.job):
                errors.append(C.WinError(C.get_last_error()))
            self.job = None
        for stream in (self.stdin, self.stdout):
            if stream and not stream.closed:
                try:
                    stream.close()
                except OSError as exc:
                    errors.append(exc)
        if self.handle:
            if not self._close(self.handle):
                errors.append(C.WinError(C.get_last_error()))
            self.handle = None
        if errors:
            raise errors[0]


def parent_memory():
    if os.name != "nt":
        return None
    kernel, psapi = C.WinDLL("kernel32", use_last_error=True), C.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.restype = W.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [W.HANDLE, C.POINTER(MemoryCounters), W.DWORD]
    counters = MemoryCounters()
    counters.cb = C.sizeof(counters)
    WindowsProcess.check(psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), C.byref(counters), C.sizeof(counters)))
    return dict(working_set_bytes=counters.ws, peak_working_set_bytes=counters.peak_ws,
                committed_bytes=counters.pagefile, peak_commit_bytes=counters.peak_pagefile)
