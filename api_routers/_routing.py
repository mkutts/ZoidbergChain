"""Shared construction for thin, contract-preserving FastAPI route adapters."""

from __future__ import annotations

from collections.abc import Iterable
from functools import wraps
from typing import Any

from fastapi import APIRouter


RouteSpec = tuple[int, str, str, str, dict[str, Any]]


def build_router(runtime: Any, specs: Iterable[RouteSpec], *, owner: str) -> APIRouter:
    """Build adapters whose signatures and metadata exactly mirror legacy handlers."""
    router = APIRouter()
    for order, method, path, handler_name, options in specs:
        implementation = getattr(runtime, handler_name)

        @wraps(implementation)
        async def endpoint(*args: Any, __implementation=implementation, **kwargs: Any) -> Any:
            return await __implementation(*args, **kwargs)

        endpoint.__module__ = owner
        endpoint.__route_order__ = order
        router.add_api_route(path, endpoint, methods=[method.upper()], **options)
    return router
