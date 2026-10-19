"""One request, then exit. Invoked only by the trusted Windows launcher."""
from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

# -I excludes environment/cwd injection. These paths come from the coordinator,
# never the media descriptor. Use the base interpreter to avoid a venv launcher
# creating a second process and violating the Job Object active-process limit.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if len(sys.argv) == 2:
    sys.path.insert(0, sys.argv[1])

from codec_prototype import worker_ipc as ipc


def main():
    # Import and pin the backend before READY; startup failures are local.
    from codec_prototype import strict_decoder as decoder
    decoder._backend()
    source, target = sys.stdin.buffer, sys.stdout.buffer
    ipc.write_message(target, dict(v=1, kind="ready"))
    request, raw = ipc.read_message(source, ipc.MAX_REQUEST)
    ipc.request_identity(request)
    if hashlib.sha256(raw).hexdigest() != request["request_sha256"] or source.read(1):
        raise ipc.IPCError("request_identity_or_trailing")
    try:
        started = time.perf_counter_ns()
        descriptor = decoder.parse_descriptor(raw)
        parse_ns = time.perf_counter_ns() - started
        started = time.perf_counter_ns()
        result = decoder.decode(descriptor)
        decode_ns = time.perf_counter_ns() - started
    except decoder.CodecReject as exc:
        ipc.write_message(target, ipc.result_header(request, "INVALID", stage=exc.stage, code=exc.code))
    except (decoder.DecoderUnavailable, MemoryError):
        ipc.write_message(target, ipc.result_header(request, "INDETERMINATE_LOCAL_FAILURE", reason="decoder_unavailable"))
    except Exception:
        ipc.write_message(target, ipc.result_header(request, "INDETERMINATE_LOCAL_FAILURE", reason="worker_internal"))
    else:
        ipc.write_message(target, ipc.result_header(request, "VALID", size=len(result.original),
                          sha256=hashlib.sha256(result.original).hexdigest(),
                          parse_ns=parse_ns, decode_ns=decode_ns), result.original)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        # No untrusted input, native messages or tracebacks on the IPC stream.
        sys.exit(70)
