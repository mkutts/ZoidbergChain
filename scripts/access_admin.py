from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from blockchain import Blockchain
import config
from wallet import Wallet


def _bootstrap_blockchain() -> Blockchain:
    return Blockchain(
        project_owner_wallet=Wallet(),
        Contributor_one=Wallet(),
        Contributor_two=Wallet(),
    )


def _safe_account_view(account: dict | None) -> dict | None:
    if not account:
        return None
    bound_wallets = list(account.get("bound_wallets", []))
    return {
        "access_account_id": account.get("access_account_id"),
        "name": account.get("name"),
        "email": account.get("email"),
        "handle": account.get("handle"),
        "status": account.get("status"),
        "max_wallets": account.get("max_wallets"),
        "wallet_count": len(bound_wallets),
        "bound_wallets": bound_wallets,
        "invite_redeemed": bool(account.get("invite_code_redeemed_at")),
        "invite_code_redeemed_at": account.get("invite_code_redeemed_at"),
        "approved_at": account.get("approved_at"),
        "last_login_at": account.get("last_login_at"),
        "notes": account.get("notes"),
        "operator_notes": account.get("operator_notes"),
        "reviewed_by": account.get("reviewed_by"),
    }


def _safe_request_view(request_record: dict | None) -> dict | None:
    if not request_record:
        return None
    return {
        "request_id": request_record.get("request_id"),
        "name": request_record.get("name"),
        "email": request_record.get("email"),
        "handle": request_record.get("handle"),
        "reason": request_record.get("reason"),
        "notes": request_record.get("notes"),
        "status": request_record.get("status"),
        "created_at": request_record.get("created_at"),
        "reviewed_at": request_record.get("reviewed_at"),
        "reviewed_by": request_record.get("reviewed_by"),
        "operator_notes": request_record.get("operator_notes"),
        "approved_access_account_id": request_record.get("approved_access_account_id"),
    }


def _safe_binding_view(binding: dict | None) -> dict | None:
    if not binding:
        return None
    return {
        "wallet_address": binding.get("wallet_address"),
        "access_account_id": binding.get("access_account_id"),
        "bound_at": binding.get("bound_at"),
        "status": binding.get("status"),
        "source": binding.get("source"),
    }


def _doctor_payload(blockchain: Blockchain) -> dict:
    storage = blockchain.storage
    return {
        "environment": config.ENVIRONMENT,
        "access_control_mode": config.ACCESS_CONTROL_MODE,
        "access_dev_bypass_enabled": config.ACCESS_DEV_BYPASS_ENABLED,
        "storage_backend": config.STORAGE_BACKEND,
        "data_dir": config.DATA_DIR,
        "node_data_dir": config.NODE_DATA_DIR,
        "sqlite_db_path": getattr(storage, "sqlite_db_path", None),
        "blockchain_file": getattr(storage, "blockchain_file", None),
        "peers_file": getattr(storage, "peers_file", None),
        "access_account_count": len(blockchain.access_accounts),
        "pending_request_count": len(blockchain.list_access_requests(status="pending")),
        "bound_wallet_count": blockchain.count_active_wallet_bindings(),
        "max_wallets_default": config.MAX_WALLETS_PER_ACCESS_ACCOUNT,
        "access_sessions_backend": "memory_only_process_local",
    }


def _print_json(payload) -> None:
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controlled-testnet access administration for ZoidbergChain.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-requests", help="List access requests.")

    approve = subparsers.add_parser("approve", help="Approve a pending access request.")
    approve.add_argument("request_id")
    approve.add_argument("--reviewed-by", default="operator")
    approve.add_argument("--operator-notes", default="")
    approve.add_argument("--max-wallets", type=int, default=config.MAX_WALLETS_PER_ACCESS_ACCOUNT)

    reject = subparsers.add_parser("reject", help="Reject an access request.")
    reject.add_argument("request_id")
    reject.add_argument("--reviewed-by", default="operator")
    reject.add_argument("--operator-notes", default="")

    create_invite = subparsers.add_parser("create-invite", help="Create an approved access account and invite code directly.")
    create_invite.add_argument("--name", required=True)
    create_invite.add_argument("--email", required=True)
    create_invite.add_argument("--handle", default="")
    create_invite.add_argument("--notes", default="")
    create_invite.add_argument("--reviewed-by", default="operator")
    create_invite.add_argument("--operator-notes", default="")
    create_invite.add_argument("--max-wallets", type=int, default=config.MAX_WALLETS_PER_ACCESS_ACCOUNT)

    suspend = subparsers.add_parser("suspend", help="Suspend an access account.")
    suspend.add_argument("access_account_id")

    list_accounts = subparsers.add_parser("list-accounts", help="List access accounts.")
    list_accounts.add_argument("--status", default="")

    show_account = subparsers.add_parser("show-account", help="Show one access account.")
    show_account.add_argument("access_account_id")

    revoke_wallet = subparsers.add_parser("revoke-wallet", help="Revoke a wallet binding.")
    revoke_wallet.add_argument("wallet_address")

    subparsers.add_parser("doctor", help="Show safe access-system diagnostics.")

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    blockchain = _bootstrap_blockchain()

    try:
        if args.command == "list-requests":
            _print_json({"requests": [_safe_request_view(item) for item in blockchain.list_access_requests()]})
            return 0

        if args.command == "approve":
            account, invite_code = blockchain.approve_access_request(
                args.request_id,
                reviewed_by=args.reviewed_by,
                operator_notes=args.operator_notes,
                max_wallets=args.max_wallets,
            )
            blockchain.save_blockchain()
            _print_json({
                "message": "Access request approved.",
                "access_account": _safe_account_view(account),
                "invite_code": invite_code,
            })
            return 0

        if args.command == "reject":
            request_record = blockchain.reject_access_request(
                args.request_id,
                reviewed_by=args.reviewed_by,
                operator_notes=args.operator_notes,
            )
            blockchain.save_blockchain()
            _print_json({"message": "Access request rejected.", "request": _safe_request_view(request_record)})
            return 0

        if args.command == "create-invite":
            account, invite_code = blockchain.create_access_invite(
                name=args.name,
                email=args.email,
                handle=args.handle,
                notes=args.notes,
                reviewed_by=args.reviewed_by,
                operator_notes=args.operator_notes,
                max_wallets=args.max_wallets,
            )
            blockchain.save_blockchain()
            _print_json({
                "message": "Access invite created.",
                "access_account": _safe_account_view(account),
                "invite_code": invite_code,
            })
            return 0

        if args.command == "suspend":
            account = blockchain.update_access_account_status(args.access_account_id, "suspended")
            blockchain.save_blockchain()
            _print_json({"message": "Access account suspended.", "access_account": _safe_account_view(account)})
            return 0

        if args.command == "list-accounts":
            status = args.status.strip() or None
            _print_json({"accounts": [_safe_account_view(item) for item in blockchain.list_access_accounts(status=status)]})
            return 0

        if args.command == "show-account":
            account = blockchain.get_access_account(args.access_account_id)
            if account is None:
                raise ValueError(f"Access account not found: {args.access_account_id}")
            _print_json({"access_account": _safe_account_view(account)})
            return 0

        if args.command == "revoke-wallet":
            binding = blockchain.revoke_wallet_binding(args.wallet_address)
            blockchain.save_blockchain()
            _print_json({"message": "Wallet binding revoked.", "wallet_binding": _safe_binding_view(binding)})
            return 0

        if args.command == "doctor":
            _print_json({"doctor": _doctor_payload(blockchain)})
            return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(run_cli())
