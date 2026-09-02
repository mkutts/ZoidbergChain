"""Task 5 characterization guards for the pre-refactor architecture."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).parent / "fixtures"
ROUTE_CONTRACT = FIXTURES_DIR / "api_route_contract.json"
IMPORT_BASELINE = FIXTURES_DIR / "architecture_import_baseline.json"
EXCLUDED_SOURCE_PARTS = {".git", ".venv", "venv", "tests", "temp", "zoidbergcoin-ui", "node_modules", "dist"}
DEV_ROUTE_NAMES = {
    "add_block",
    "cleanup_bad_mint_queue_items",
    "dev_debug",
    "dev_reset_blockchain",
    "generate_wallet",
    "get_dev_wallets",
    "get_wallets",
    "repair_submission_certificate",
    "reset_blockchain",
}


def _route_security(route):
    dependencies = sorted(
        {
            getattr(getattr(dependency, "call", None), "__name__", "")
            for dependency in route.dependant.dependencies
        }
        - {""}
    )
    return dependencies, {
        "authentication_expected": any(name in {"_verified_wallet_dependency", "_require_admin_session", "require_peer_secret"} for name in dependencies),
        "authorization_expected": any("access" in name or name in {"_require_admin_session", "require_peer_secret"} for name in dependencies),
    }


def _route_classification(route):
    if route.path.startswith("/admin"):
        return "admin"
    dependencies, _ = _route_security(route)
    if route.path.startswith("/peers") and "require_peer_secret" in dependencies:
        return "peer"
    if route.path.startswith("/dev") or route.name in DEV_ROUTE_NAMES:
        return "development"
    return "public"


def _route_contract():
    # Importing the app is intentional here; subprocess import isolation is tested below.
    import api

    excluded = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    rows = []
    for route in api.app.routes:
        if not hasattr(route, "methods") or route.path in excluded:
            continue
        dependencies, security = _route_security(route)
        request_models = sorted(
            {
                annotation.__name__
                for parameter in route.dependant.body_params
                if (annotation := getattr(parameter.field_info, "annotation", None))
                and hasattr(annotation, "model_fields")
            }
        )
        response_model = getattr(route, "response_model", None)
        for method in sorted(set(route.methods or ()) - {"HEAD", "OPTIONS"}):
            rows.append(
                {
                    "method": method,
                    "path": route.path,
                    "name": route.name,
                    "classification": _route_classification(route),
                    "authentication_expected": security["authentication_expected"],
                    "authorization_expected": security["authorization_expected"],
                    "security_dependencies": dependencies,
                    "request_model": ", ".join(request_models) or None,
                    "response_model": getattr(response_model, "__name__", None),
                    "declared_status_code": route.status_code,
                }
            )
    return sorted(rows, key=lambda row: (row["path"], row["method"], row["name"]))


def test_api_route_contract(monkeypatch, isolated_data_dir):
    """Routes, security boundaries, and declared models change only intentionally."""
    monkeypatch.chdir(isolated_data_dir)
    actual = _route_contract()
    if os.environ.get("UPDATE_API_ROUTE_CONTRACT") == "1":
        ROUTE_CONTRACT.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
        pytest.skip("API route contract fixture regenerated")
    expected = json.loads(ROUTE_CONTRACT.read_text(encoding="utf-8"))
    assert actual == expected


def _source_modules():
    modules = {}
    for root, directories, files in os.walk(PROJECT_ROOT):
        directories[:] = [name for name in directories if name not in EXCLUDED_SOURCE_PARTS]
        relative_root = Path(root).relative_to(PROJECT_ROOT)
        if relative_root.parts and relative_root.parts[0] == "scripts":
            directories[:] = []
            continue
        for filename in files:
            if not filename.endswith(".py"):
                continue
            path = Path(root) / filename
            relative = path.relative_to(PROJECT_ROOT)
            module = ".".join(relative.with_suffix("").parts)
            modules[module] = path
    return modules


def _import_graph():
    modules = _source_modules()
    graph = {module: set() for module in modules}
    imports = {module: [] for module in modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    if imported in modules:
                        graph[module].add(imported)
                        imports[module].append((imported, node.lineno))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module
                if node.level:
                    prefix = module.split(".")[:-node.level]
                    imported = ".".join(prefix + [imported])
                if imported in modules:
                    graph[module].add(imported)
                    imports[module].append((imported, node.lineno))
    return graph, imports


def _strongly_connected_components(graph):
    index = 0
    indices, lowlinks, stack, on_stack, components = {}, {}, [], set(), []

    def visit(node):
        nonlocal index
        indices[node] = lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for child in sorted(graph[node]):
            if child not in indices:
                visit(child)
                lowlinks[node] = min(lowlinks[node], lowlinks[child])
            elif child in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[child])
        if lowlinks[node] == indices[node]:
            component = sorted(stack[stack.index(node) :])
            del stack[stack.index(node) :]
            on_stack.difference_update(component)
            if len(component) > 1 or node in graph[node]:
                components.append(component)

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return sorted(components)


def _current_import_findings():
    graph, imports = _import_graph()
    violations = []
    protocol_modules = {name for name in graph if name.startswith("protocol_v1")}
    domain_modules = {
        "access_control", "admin_auth", "auth", "block", "blockchain", "config", "content",
        "native_transfer", "originality_certificate", "ops_support", "review_policy", "submission",
        "transaction", "utils", "validators", "wallet", "wallet_auth",
    }
    storage_modules = {"storage", "storage_migration", "storage_tools"}
    peer_modules = {"peer_sync", "peers", "sync"}
    for source, edges in imports.items():
        for target, line in edges:
            forbidden = (
                (source in protocol_modules and target == "api")
                or (source in domain_modules and target == "api")
                or (source in storage_modules and target == "api")
                or (source in peer_modules and target == "api")
            )
            if forbidden:
                violations.append({"source": source, "target": target, "line": line})
    fastapi_imports = []
    for source in protocol_modules:
        tree = ast.parse(_source_modules()[source].read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            names = node.names if isinstance(node, ast.Import) else [node] if isinstance(node, ast.ImportFrom) else []
            for item in names:
                name = item.name if isinstance(node, ast.Import) else node.module or ""
                if name == "fastapi" or name.startswith("fastapi."):
                    fastapi_imports.append({"source": source, "target": name, "line": node.lineno})
    return {"forbidden_edges": sorted(violations, key=lambda item: (item["source"], item["target"], item["line"])), "protocol_fastapi_imports": sorted(fastapi_imports, key=lambda item: (item["source"], item["line"])), "cycles": _strongly_connected_components(graph)}


def test_architecture_import_boundaries_and_cycles():
    """AST-only graph guard: existing debt is narrowly baselined, new debt fails."""
    actual = _current_import_findings()
    if os.environ.get("UPDATE_ARCHITECTURE_IMPORT_BASELINE") == "1":
        IMPORT_BASELINE.write_text(json.dumps(actual, indent=2) + "\n", encoding="utf-8")
        pytest.skip("architecture import baseline fixture regenerated")
    expected = json.loads(IMPORT_BASELINE.read_text(encoding="utf-8"))
    assert actual == expected, json.dumps({"expected": expected, "actual": actual}, indent=2)


@pytest.mark.parametrize("module", ["protocol_v1", "blockchain", "api"])
def test_imports_do_not_create_repository_root_runtime_state(module, tmp_path):
    """Import from a controlled subprocess and verify root data paths stay untouched."""
    names = ["blockchain.json", "peers.json", "wallets.json", "zoidbergchain.db", "content", "blockchain.json.bak", "peers.json.bak"]
    before = {name: (PROJECT_ROOT / name).exists() for name in names}
    isolated = tmp_path / "import-state"
    isolated.mkdir()
    environment = os.environ.copy()
    environment.update({"NODE_DATA_DIR": str(isolated), "CONTENT_STORAGE_DIR": str(isolated / "content"), "LOG_DIR": str(isolated / "logs"), "PYTHONPATH": str(PROJECT_ROOT), "ENVIRONMENT": "development"})
    result = subprocess.run([sys.executable, "-c", f"import {module}"], cwd=isolated, env=environment, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert {name: (PROJECT_ROOT / name).exists() for name in names} == before
