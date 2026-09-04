"""Task 11 route ownership, thin-adapter, and import-isolation guards."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.routing import APIRoute


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPLICATION_ROUTE_COUNT = 129
EXPECTED_ROUTER_COUNTS = {
    "api_routers.access": 16,
    "api_routers.admin": 29,
    "api_routers.content": 20,
    "api_routers.native": 23,
    "api_routers.operations": 16,
    "api_routers.peer": 20,
    "api_routers.public_chain": 5,
}


def _application_routes():
    import api

    return [route for route in api.app.routes if isinstance(route, APIRoute)]


def _dependency_names(route: APIRoute) -> set[str]:
    return {
        getattr(getattr(dependency, "call", None), "__name__", "")
        for dependency in route.dependant.dependencies
    }


def test_all_129_routes_have_one_domain_router_and_preserve_global_order():
    routes = _application_routes()
    assert len(routes) == APPLICATION_ROUTE_COUNT
    assert [route.endpoint.__route_order__ for route in routes] == list(range(APPLICATION_ROUTE_COUNT))

    actual_counts = {
        owner: sum(route.endpoint.__module__ == owner for route in routes)
        for owner in EXPECTED_ROUTER_COUNTS
    }
    assert actual_counts == EXPECTED_ROUTER_COUNTS


def test_openapi_contains_every_frozen_contract_operation():
    import api

    contract = json.loads(
        (PROJECT_ROOT / "tests" / "fixtures" / "api_route_contract.json").read_text(encoding="utf-8")
    )
    schema_paths = api.app.openapi()["paths"]
    for row in contract:
        operation = schema_paths[row["path"]][row["method"].lower()]
        assert operation["operationId"].startswith(f'{row["name"]}_')


def test_public_admin_peer_and_development_boundaries_are_separate():
    routes = _application_routes()
    admin_routes = [route for route in routes if route.endpoint.__module__ == "api_routers.admin"]
    operations_routes = [route for route in routes if route.endpoint.__module__ == "api_routers.operations"]
    peer_routes = [route for route in routes if route.endpoint.__module__ == "api_routers.peer"]
    public_chain_routes = [route for route in routes if route.endpoint.__module__ == "api_routers.public_chain"]

    assert admin_routes and all(route.path.startswith("/admin") for route in admin_routes)
    session_lifecycle_paths = {"/admin/login", "/admin/logout", "/admin/session"}
    assert all(
        "_require_admin_session" in _dependency_names(route)
        for route in admin_routes
        if route.path not in session_lifecycle_paths
    )
    assert all(not route.path.startswith("/admin") for route in public_chain_routes)
    assert all("_require_admin_session" not in _dependency_names(route) for route in public_chain_routes)

    development_names = {
        "add_block", "cleanup_bad_mint_queue_items", "dev_debug", "dev_reset_blockchain",
        "generate_wallet", "get_dev_wallets", "get_wallets", "repair_submission_certificate",
        "reset_blockchain",
    }
    assert development_names <= {route.name for route in operations_routes}

    authenticated_peer_routes = [
        route for route in peer_routes
        if route.path.startswith("/peers") and "require_peer_secret" in _dependency_names(route)
    ]
    assert authenticated_peer_routes
    assert all("_require_admin_session" not in _dependency_names(route) for route in peer_routes)


def test_11a_target_routers_are_explicit_http_adapters():
    router_dir = PROJECT_ROOT / "api_routers"
    for name in ("public_chain", "access", "admin"):
        source = (router_dir / f"{name}.py").read_text(encoding="utf-8")
        assert "EXPLICIT_ROUTER = True" in source
        assert "@router." in source
        assert "*args" not in source and "**kwargs" not in source
        assert "getattr(runtime" not in source


def test_11b_content_and_native_are_explicit_and_runtime_no_longer_owns_them():
    router_dir = PROJECT_ROOT / "api_routers"
    runtime_tree = ast.parse((PROJECT_ROOT / "api_runtime.py").read_text(encoding="utf-8"))
    runtime_functions = {
        node.name for node in runtime_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name, count in (("content", 20), ("native", 23)):
        source = (router_dir / f"{name}.py").read_text(encoding="utf-8")
        assert "EXPLICIT_ROUTER = True" in source
        assert source.count("@router.") >= count
        route_names = {
            route.name for route in _application_routes()
            if route.endpoint.__module__ == f"api_routers.{name}"
        }
        assert not (route_names & runtime_functions)


def test_11b_content_and_native_mutations_use_facade_operations_only():
    router_dir = PROJECT_ROOT / "api_routers"
    forbidden = {
        "save_blockchain(", "Transaction(", ".sign_transaction(",
        ".mint_submission(", ".cast_submission_vote(",
        ".admit_transaction_to_mempool(", ".revalidate_mempool_transactions(",
        ".verify_submission_signature(", ".verify_vote_signature(",
        ".verify_transfer_signature(",
    }
    required = {
        "content": {
            "upload_binary_content_operation", "upload_text_content_operation",
            "verify_content_download_operation", "submit_signed_content_operation",
            "submit_content_operation", "cast_signed_submission_vote_operation",
            "cast_development_submission_vote_operation", "evaluate_submission_operation",
            "get_mint_queue_operation", "mint_submission_operation",
            "block_submission_minting_operation", "unblock_submission_minting_operation",
        },
        "native": {
            "submit_signed_transfer_operation", "legacy_add_transaction_operation",
            "admit_native_transaction_operation", "revalidate_mempool_operation",
        },
    }
    for name, operation_names in required.items():
        source = (router_dir / f"{name}.py").read_text(encoding="utf-8")
        assert not any(token in source for token in forbidden)
        assert all(operation in source for operation in operation_names)


def test_11c_peer_and_operations_are_explicit_and_runtime_has_no_route_handlers():
    router_dir = PROJECT_ROOT / "api_routers"
    runtime_tree = ast.parse((PROJECT_ROOT / "api_runtime.py").read_text(encoding="utf-8"))
    runtime_functions = {
        node.name for node in runtime_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name, count in (("peer", 20), ("operations", 16)):
        source = (router_dir / f"{name}.py").read_text(encoding="utf-8")
        assert "EXPLICIT_ROUTER = True" in source
        assert source.count("@router.") >= count
        route_names = {
            route.name for route in _application_routes()
            if route.endpoint.__module__ == f"api_routers.{name}"
        }
        assert not (route_names & runtime_functions)
    assert not any(
        isinstance(node, ast.AsyncFunctionDef)
        and any(isinstance(decorator, ast.Call) and getattr(decorator.func, "id", "") == "api_limit"
                for decorator in node.decorator_list)
        for node in runtime_tree.body
    )


def test_11c_mutating_peer_and_operations_routes_use_service_or_facade_boundaries():
    router_dir = PROJECT_ROOT / "api_routers"
    peer_source = (router_dir / "peer.py").read_text(encoding="utf-8")
    operations_source = (router_dir / "operations.py").read_text(encoding="utf-8")
    assert not any(token in peer_source for token in {
        "save_blockchain(", "peer_store.register_peer(", "content_object.hash_scheme =",
        "content_object.verified_at =", "content_object.storage_status =",
    })
    assert "register_peer_operation(" in peer_source
    assert "verify_content_download_operation(" in peer_source
    assert not any(token in operations_source for token in {
        "save_blockchain(", "Wallet(", "blockchain.add_block(",
        "create_originality_certificate(", "blockchain.cleanup_bad_mint_queue_items(",
        "os.makedirs(", "open(", "os.remove(",
    })
    for operation in {
        "reset_runtime_blockchain_operation(", "repair_submission_certificate_operation(",
        "legacy_add_block_upload_operation(", "generate_development_wallet_operation(",
        "cleanup_bad_mint_queue_items_operation(",
    }:
        assert operation in operations_source


def test_11a2_access_and_admin_mutations_use_facade_operations_only():
    router_dir = PROJECT_ROOT / "api_routers"
    forbidden = {
        "save_blockchain", "_persist_transition", "append_audit_log_entry",
        "create_feedback", "create_access_request", "create_access_invite",
        "approve_access_request", "reject_access_request", "create_allowlist_entry",
        "update_allowlist_entry", "revoke_allowlist_entry", "reactivate_allowlist_entry",
        "create_override_request", "update_override_request_status", "update_feedback",
        "add_feedback_admin_note", "update_access_account_status", "revoke_wallet_binding",
        "bind_wallet_to_access_account", "mark_access_account_login",
        "refresh_access_control_state_from_storage",
    }
    required = {
        "access": {
            "submit_feedback_operation", "submit_access_request_operation",
            "complete_access_login_operation", "bind_access_wallet_operation",
            "submit_override_request_operation",
        },
        "admin": {
            "approve_access_request_operation", "reject_access_request_operation",
            "create_access_invite_operation", "create_allowlist_entry_operation",
            "update_allowlist_entry_operation", "revoke_allowlist_entry_operation",
            "reactivate_allowlist_entry_operation", "approve_override_request_operation",
            "reject_override_request_operation", "update_feedback_operation",
            "update_feedback_status_operation", "add_feedback_note_operation",
            "revoke_wallet_binding_operation", "update_access_account_status_operation",
        },
    }
    for name, expected_operations in required.items():
        tree = ast.parse((router_dir / f"{name}.py").read_text(encoding="utf-8"))
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert expected_operations <= calls
        assert not (forbidden & calls), (name, forbidden & calls)


def test_router_modules_do_not_own_low_level_domain_transitions():
    router_dir = PROJECT_ROOT / "api_routers"
    forbidden_calls = {"save_blockchain", "add_block", "replace_chain", "sign", "persist"}
    for path in router_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(name == "services" or name.startswith("services.") for name in names), path
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in forbidden_calls, f"{path}:{node.lineno} calls {node.func.attr}"


def test_services_do_not_import_api_runtime_or_routers():
    for path in (PROJECT_ROOT / "services").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not any(name in {"api", "api_runtime"} or name.startswith("api_routers") for name in imported), path


def test_importing_application_and_routers_creates_no_repository_root_state(tmp_path):
    state_names = (
        "blockchain.json", "blockchain.json.bak", "peers.json", "peers.json.bak",
        "wallets.json", "zoidbergchain.db", "content",
    )
    before = {
        name: ((path := PROJECT_ROOT / name).exists(), path.stat().st_mtime_ns if path.exists() else None)
        for name in state_names
    }
    isolated = tmp_path / "router-imports"
    isolated.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "NODE_DATA_DIR": str(isolated),
            "CONTENT_STORAGE_DIR": str(isolated / "content"),
            "LOG_DIR": str(isolated / "logs"),
            "PYTHONPATH": str(PROJECT_ROOT),
            "ENVIRONMENT": "development",
        }
    )
    modules = ["api", "api_runtime", *EXPECTED_ROUTER_COUNTS]
    result = subprocess.run(
        [sys.executable, "-c", "; ".join(f"import {module}" for module in modules)],
        cwd=isolated,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    after = {
        name: ((path := PROJECT_ROOT / name).exists(), path.stat().st_mtime_ns if path.exists() else None)
        for name in state_names
    }
    assert after == before
