import subprocess
import sys
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parents[1]
    test_targets = [
        "tests/integration/test_two_node_consensus_verification.py",
        "tests/api/test_peer_certificate_sync_api.py",
        "tests/api/test_chain_sync_api.py",
        "tests/api/test_peer_block_sync_api.py",
    ]
    command = [sys.executable, "-m", "pytest", *test_targets]
    print("Running two-node consensus verification:", flush=True)
    print(" ".join(command), flush=True)
    return subprocess.call(command, cwd=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
