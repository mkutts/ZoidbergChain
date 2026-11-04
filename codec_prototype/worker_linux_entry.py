"""Trusted Linux bootstrap; no request bytes read until confinement succeeds."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from codec_prototype import worker_ipc as ipc
    from codec_prototype.worker_linux import IsolationUnavailable, prepare, confine
    try:
        if len(sys.argv) != 6:
            raise IsolationUnavailable("linux_launcher_arguments")
        try:
            prepare(int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[5]))
        except IsolationUnavailable:
            raise
        except (OSError, AttributeError, ValueError) as exc:
            raise IsolationUnavailable("linux_bootstrap_unavailable") from exc
        # Trusted runtime path supplied only by the coordinator, never media.
        sys.path.insert(0, sys.argv[4])
        from codec_prototype.worker_entry import main as decode_one
        from codec_prototype.strict_decoder import DecoderUnavailable
        try:
            decode_one(before_ready=confine)
        except DecoderUnavailable as exc:
            raise IsolationUnavailable("linux_backend_unavailable") from exc
    except IsolationUnavailable as exc:
        ipc.write_message(sys.stdout.buffer, dict(v=1, kind="unavailable", reason=exc.reason))
    except (ImportError, MemoryError):
        ipc.write_message(sys.stdout.buffer, dict(v=1, kind="unavailable", reason="linux_backend_unavailable"))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        sys.exit(70)
