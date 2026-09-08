import inspect

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute

from ._compat import unwrap_route
from ._deprecation import DeprecationPolicy, attach_headers, deprecation_route_class
from ._docs import DocsMounter
from ._scheme import VersionScheme, version_gte
from ._versions import _ATTR_DEPRECATE_IN, VersionT


class VersionRouterBuilder:
    """The routers the caller handed to RouterVersioner are never modified: each version gets
    its own copy of every route still active in it, carrying only the methods still assigned to
    it there, plus that version's documentation routes.
    """

    def __init__(
        self,
        app: FastAPI,
        scheme: VersionScheme,
        docs: DocsMounter,
        deprecation: DeprecationPolicy,
        *,
        sort_routes: bool,
    ) -> None:
        self._app = app
        self._scheme = scheme
        self._docs = docs
        self._deprecation = deprecation
        self._sort_routes = sort_routes

    def build(
        self,
        version: VersionT,
        version_prefix: str,
        routes_by_key: dict[tuple[str, str], Any],
        webhooks: list[Any],
        routes_by_version: dict[VersionT, dict[tuple[str, str], Any]],
    ) -> APIRouter:
        router = APIRouter(prefix=version_prefix, responses=self._app.router.responses)

        if self._sort_routes:
            routes_by_key = dict(sorted(routes_by_key.items()))

        grouped_routes: dict[int, tuple[Any, set[str]]] = {}
        for (_path, method), keyed_route in routes_by_key.items():
            route_id = id(keyed_route)
            if route_id not in grouped_routes:
                grouped_routes[route_id] = (keyed_route, set())
            if method:
                grouped_routes[route_id][1].add(method)

        for route, active_methods in grouped_routes.values():
            self._add_route(
                route=route,
                router=router,
                version=version,
                active_methods=active_methods or None,
                header_set=self._deprecation.headers_for(route, version, routes_by_version),
            )

        self._docs.mount(router=router, version=version, version_prefix=version_prefix, webhooks=webhooks)

        return router

    def _add_route(
        self,
        route: Any,
        router: APIRouter,
        version: VersionT,
        active_methods: set[str] | None = None,
        header_set: dict[str, str] | None = None,
    ) -> None:
        source_route = unwrap_route(route)
        add_method: Callable[..., Any]

        if isinstance(source_route, APIRoute):
            add_method = router.add_api_route
        elif isinstance(source_route, APIWebSocketRoute):
            add_method = router.add_api_websocket_route
        else:
            raise TypeError(f"Unsupported route type: {type(source_route).__name__}")

        valid_params = inspect.signature(add_method).parameters.keys()
        filtered_kwargs = {k: getattr(route, k) for k in valid_params if hasattr(route, k)}
        filtered_kwargs.setdefault("endpoint", source_route.endpoint)
        # route_class_override isn't an attribute of the route instance (add_api_route consumes
        # it once, at construction time), so the comprehension above never captures it: without
        # this, a router built with APIRouter(route_class=CustomRoute) would silently remount
        # every route as a plain APIRoute, dropping whatever get_route_handler() overrides.
        if isinstance(source_route, APIRoute):
            route_class = type(source_route)
            # Only APIRoute gets here: a WebSocket has no response to put headers on.
            if header_set:
                route_class = deprecation_route_class(route_class)
                attach_headers(source_route.endpoint, f"{router.prefix}{route.path}", header_set)
            filtered_kwargs["route_class_override"] = route_class
        # A sibling route may have taken over some of this route's original methods at this
        # version: mount only the methods still assigned to it, not its full original set.
        if active_methods is not None and "methods" in valid_params:
            filtered_kwargs["methods"] = active_methods

        deprecated_in_version = self._scheme.extract(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
        # add_api_websocket_route has no 'deprecated': a WebSocket route has no OpenAPI presence.
        if (
            "deprecated" in valid_params
            and deprecated_in_version is not None
            and version_gte(version, deprecated_in_version)
        ):
            filtered_kwargs["deprecated"] = True

        # An empty string name causes an internal FastAPI error; drop it to use the default.
        if "name" in filtered_kwargs and not filtered_kwargs["name"]:
            filtered_kwargs.pop("name")

        add_method(**filtered_kwargs)
