"""Fix or inspect the Public Testnet admission activation height.

Run against each stopped node's configured NODE_DATA_DIR.  The first node may
choose --next-block; all other nodes must receive that exact --height value.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blockchain import Blockchain
from storage import create_storage_backend


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--show", action="store_true", help="Show the current fixed height and canonical tip.")
    choice.add_argument("--next-block", action="store_true", help="Fix height to this node's tip plus one.")
    choice.add_argument("--height", type=int, help="Fix the exact network-wide height chosen on the first node.")
    args = parser.parse_args(argv)

    backend = create_storage_backend()
    document = backend.load_blockchain_state()
    if not isinstance(document, dict) or not document.get("chain"):
        parser.error("An existing canonical genesis/chain is required; check NODE_DATA_DIR.")
    chain = Blockchain(storage_backend=backend)
    if args.show:
        result = chain.admission_activation_status()
    else:
        result = chain.configure_admission_activation(
            None if args.next_block else args.height)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
