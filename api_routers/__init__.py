"""Domain-router assembly for the ZoidbergChain FastAPI application."""

from __future__ import annotations

import sys
import importlib
from typing import Any

from fastapi import FastAPI

from . import access, admin, content, native, operations, peer, public_chain


ROUTER_MODULES = {
    "public_chain": public_chain,
    "access": access,
    "admin": admin,
    "content": content,
    "native": native,
    "peer": peer,
    "operations": operations,
}
DOMAIN_ROUTERS = {name: module.router for name, module in ROUTER_MODULES.items()}


def install_routers(app: FastAPI, runtime: Any) -> None:
    """Install every domain route in its pre-refactor global order exactly once."""
    if getattr(app.state, "domain_routers_installed", False):
        return

    DOMAIN_ROUTERS.clear()
    for name, module in tuple(ROUTER_MODULES.items()):
        # Test and multi-node loaders may have imported an isolated runtime
        # between API reloads. Re-resolve the named router before rebuilding it
        # so a cached package attribute can never select that runtime module.
        module = importlib.import_module(f"{__name__}.{name}")
        ROUTER_MODULES[name] = module
        if (
            getattr(module, "EXPLICIT_ROUTER", False)
            and getattr(module, "_ROUTER_RUNTIME_GENERATION", None)
            is not getattr(runtime, "_ROUTER_RUNTIME_GENERATION", None)
        ):
            module = importlib.reload(module)
            ROUTER_MODULES[name] = module
        # Every Task 11 domain module owns concrete FastAPI endpoints.  A
        # generic forwarding builder would weaken the route-ownership boundary.
        if not getattr(module, "EXPLICIT_ROUTER", False):
            raise RuntimeError(f"Router module must declare explicit endpoints: {module.__name__}")
        DOMAIN_ROUTERS[name] = module.router

    ordered_routes = sorted(
        (route for router in DOMAIN_ROUTERS.values() for route in router.routes),
        key=lambda route: route.endpoint.__route_order__,
    )
    # FastAPI 0.115+ stores include_router() calls lazily.  The historical route
    # contract intentionally inspects app.routes, so install the already-built
    # APIRoute objects directly while retaining APIRouter ownership by domain.
    app.router.routes.extend(ordered_routes)
    app.state.domain_routers_installed = True
    runtime.domain_routers = dict(DOMAIN_ROUTERS)


# Support direct ``import api_routers`` while ``api_runtime`` is importing the
# package: the runtime's bootstrap call necessarily occurs before this module's
# symbols exist, so complete installation once package initialization finishes.
_runtime = sys.modules.get("api_runtime")
if _runtime is not None and hasattr(_runtime, "app"):
    install_routers(_runtime.app, _runtime)
