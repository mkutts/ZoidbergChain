import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from tests.integration.two_node_native_transfer_harness import run_two_node_native_transfer_verification


def main():
    try:
        run_two_node_native_transfer_verification(verbose=True)
        return 0
    except Exception as exc:
        print(f"TWO-NODE NATIVE TRANSFER TEST FAILED: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
