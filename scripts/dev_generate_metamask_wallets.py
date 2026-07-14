from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from eth_keys import keys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEV_ONLY_WARNING = "DEV ONLY - DO NOT USE THESE WALLETS WITH REAL FUNDS"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_development_only() -> None:
    if not config.is_development():
        raise ValueError("Dev wallet generation is only allowed when ENVIRONMENT=development.")
    if config.public_api_mode_enabled():
        raise ValueError("Dev wallet generation is not allowed when PUBLIC_API_MODE=true.")


def _default_output_path(fmt: str) -> Path:
    return (PROJECT_ROOT / "data" / f"dev_wallets.{fmt}").resolve()


def generate_wallet_records(count: int = 5) -> list[dict[str, str]]:
    _ensure_development_only()
    if count <= 0:
        raise ValueError("Wallet count must be greater than zero.")

    wallets: list[dict[str, str]] = []
    for index in range(1, count + 1):
        private_key_bytes = os.urandom(32)
        private_key = keys.PrivateKey(private_key_bytes)
        wallets.append(
            {
                "label": f"dev-wallet-{index}",
                "address": private_key.public_key.to_checksum_address(),
                "private_key": private_key_bytes.hex(),
            }
        )
    return wallets


def write_wallet_export(
    wallets: list[dict[str, str]],
    *,
    output_path: str | Path | None = None,
    fmt: str = "json",
) -> Path:
    fmt = (fmt or "json").strip().lower()
    if fmt not in {"json", "csv"}:
        raise ValueError("Unsupported export format. Use json or csv.")

    destination = Path(output_path).resolve() if output_path else _default_output_path(fmt)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        payload = {
            "warning": DEV_ONLY_WARNING,
            "generated_at": _utc_now(),
            "wallets": wallets,
        }
        destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        with destination.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["label", "address", "private_key"])
            writer.writeheader()
            writer.writerows(wallets)

    return destination


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate dev-only MetaMask-compatible wallet keys for local testing."
    )
    parser.add_argument("--count", type=int, default=5, help="Number of wallets to generate. Default: 5.")
    parser.add_argument("--output", help="Output file path. Defaults to data/dev_wallets.<format>.")
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["json", "csv"],
        default="json",
        help="Export format. Default: json.",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_cli_parser()
    try:
        args = parser.parse_args(argv)
        wallets = generate_wallet_records(args.count)
        output_path = write_wallet_export(wallets, output_path=args.output, fmt=args.fmt)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    result = {
        "warning": DEV_ONLY_WARNING,
        "generated_at": _utc_now(),
        "count": len(wallets),
        "format": args.fmt,
        "output_path": str(output_path),
        "wallets": wallets,
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
