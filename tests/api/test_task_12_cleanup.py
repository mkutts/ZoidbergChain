"""Task 12 regression guards for removal of the obsolete router fallback."""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTER_MODULES = (
    "access",
    "admin",
    "content",
    "native",
    "operations",
    "peer",
    "public_chain",
)


def test_router_assembly_has_no_generic_forwarding_fallback():
    """All installed routes must be concrete domain adapters, not generated wrappers."""
    router_dir = PROJECT_ROOT / "api_routers"
    assert not (router_dir / "_routing.py").exists()

    package_tree = ast.parse((router_dir / "__init__.py").read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(package_tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert "build_router" not in imports

    for name in ROUTER_MODULES:
        source = (router_dir / f"{name}.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "EXPLICIT_ROUTER = True" in source
        assert not any(
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ROUTES" for target in node.targets)
            for node in tree.body
        )

    import api

    routes = [route for route in api.app.routes if isinstance(route, APIRoute)]
    assert len(routes) == 129
    assert [route.endpoint.__route_order__ for route in routes] == list(range(129))
    assert {route.endpoint.__module__ for route in routes} == {
        f"api_routers.{name}" for name in ROUTER_MODULES
    }
