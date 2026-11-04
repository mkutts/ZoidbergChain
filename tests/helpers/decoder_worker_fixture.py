"""Trusted fault-injection executable, never selectable through media or API."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, sys.argv[1])  # Trusted test venv, like the real launcher.
from codec_prototype import worker_ipc as ipc


def main():
    mode = sys.argv[2]
    if mode == "controller":
        from codec_prototype.isolated_decoder import IsolatedDecoder, Limits
        class Controller(IsolatedDecoder):
            def _command(self):
                return [sys._base_executable, "-I", "-u", __file__, sys.argv[1], "hang"]
            def _spawn(self):
                process = super()._spawn()
                print(process.pid, flush=True)
                return process
        pool = Controller(limits=Limits(wall_seconds=60))
        raw = Path(sys.argv[3]).read_bytes()
        pool.validate(raw)
        return
    if mode == "startup_hang":
        time.sleep(60)
        return
    source, target = sys.stdin.buffer, sys.stdout.buffer
    ipc.write_message(target, dict(v=1, kind="ready"))
    request, raw = ipc.read_message(source, ipc.MAX_REQUEST)
    ipc.request_identity(request)
    assert not source.read(1)
    assert hashlib.sha256(raw).hexdigest() == request["request_sha256"]
    if mode == "crash":
        os._exit(23)
    if mode == "hang":
        time.sleep(60)
    elif mode == "spin":
        while True:
            pass
    elif mode == "allocate":
        try:
            data = bytearray(64 * 1024 * 1024)
        except MemoryError:
            reason = "memory_limit_confirmed"
        else:
            reason = "memory_limit_missing"
            del data
        ipc.write_message(target, ipc.result_header(request, "INDETERMINATE_LOCAL_FAILURE", reason=reason))
    elif mode == "spawn_child":
        try:
            child = subprocess.Popen([sys.executable, "-I", "-c", "pass"], creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError:
            reason = "child_limit_confirmed"
        else:
            child.wait(timeout=2)
            reason = "child_limit_missing"
        ipc.write_message(target, ipc.result_header(request, "INDETERMINATE_LOCAL_FAILURE", reason=reason))
    elif mode == "oversized":
        target.write(ipc.PREFIX.pack(ipc.MAGIC, 1, ipc.MAX_OUTPUT + 1))
        target.flush()
    elif mode == "truncated":
        target.write(ipc.PREFIX.pack(ipc.MAGIC, 100, 0) + b"{")
        target.flush()
    elif mode == "malformed":
        target.write(ipc.PREFIX.pack(ipc.MAGIC, 3, 0) + b"bad")
        target.flush()
    elif mode == "duplicate":
        header = b'{"v":1,"v":1}'
        target.write(ipc.PREFIX.pack(ipc.MAGIC, len(header), 0) + header)
        target.flush()
    elif mode == "unknown_status":
        ipc.write_message(target, ipc.result_header(request, "MAYBE"))
    else:
        desc = json.loads(raw)
        body = b"abc"
        meta = ipc.result_header(request, "VALID", size=len(body), sha256=desc["original_sha256"], parse_ns=0, decode_ns=0)
        if mode == "wrong_id":
            meta["id"] = ("0" if meta["id"][0] != "0" else "1") + meta["id"][1:]
        elif mode == "wrong_request":
            meta["request_sha256"] = "0" * 64
        elif mode == "wrong_hash":
            body = b"bad"
        elif mode == "wrong_size":
            meta["size"] += 1
        elif mode == "excess_body":
            body += b"x"
            meta["size"] += 1
        elif mode == "extra_field":
            meta["unexpected"] = 1
        ipc.write_message(target, meta, body)
        if mode == "trailing":
            target.write(b"x")
            target.flush()
        elif mode == "exit_after_reply":
            os._exit(23)
        elif mode == "close_then_hang":
            target.close()
            time.sleep(60)


if __name__ == "__main__":
    main()
