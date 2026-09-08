"""The one place that adapts to FastAPI's own route representation, which changed shape in
0.137.2. Everything else in this package works on whatever these two functions hand back.
"""

from collections.abc import Callable, Iterator
from typing import Any

import fastapi.routing

from fastapi.routing import APIRoute, APIWebSocketRoute

# iter_route_contexts was introduced in FastAPI 0.137.2. On older versions the
# attribute does not exist and getattr returns None, activating the fallback path.
_route_contexts_fn: Callable[..., Any] | None = getattr(fastapi.routing, "iter_route_contexts", None)


def iter_routes_flat(routes: list[Any]) -> Iterator[Any]:
    """
    Flattens the route tree using iter_route_contexts (FastAPI >= 0.137.2),
    or yields the original flat list for older versions.
    """
    if _route_contexts_fn is None:
        yield from routes
        return

    for route_ctx in _route_contexts_fn(routes):
        original = route_ctx.original_route
        if isinstance(original, APIRoute):
            # RouteContext merges path/tags/deps via __getattr__; use the context directly.
            yield route_ctx
        elif isinstance(original, APIWebSocketRoute):
            # For WebSockets, RouteContext.__getattr__ does NOT merge parent prefixes into path.
            # _route_context._EffectiveRouteContext holds the fully resolved starlette_route
            # (with all include_router prefixes applied). Fall back to original for direct routes.
            rc = getattr(route_ctx, "_route_context", None)
            starlette_route = getattr(rc, "starlette_route", None) if rc is not None else None
            yield starlette_route if starlette_route is not None else original
        else:
            yield original  # pragma: no cover


def unwrap_route(route: Any) -> Any:
    # RouteContext (FastAPI >= 0.137.2) wraps the original route.
    # Attributes like response_model, status_code, operation_id live on the original.
    return getattr(route, "original_route", route)
