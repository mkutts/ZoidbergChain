from __future__ import annotations

import sys
from pathlib import Path


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from storage_tools import run_cli


if __name__ == "__main__":
    raise SystemExit(run_cli(["export", *sys.argv[1:]]))
