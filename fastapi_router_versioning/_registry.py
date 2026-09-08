"""What several RouterVersioner instances sharing one FastAPI app have to agree on: which
prefixes are taken, who contributes to the aggregated /versions payload, and which of them
mounted the shared /versions and dashboard routes.
"""

from collections.abc import Callable
from typing import Any
from weakref import WeakKeyDictionary

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from ._dashboard import render_versions_dashboard


class _AppRegistry:
    """Cross-instance bookkeeping for multiple RouterVersioner sharing one app: claimed
    prefixes (collision detection), the version-model providers feeding the aggregated
    /versions endpoint and its HTML dashboard, and a mount latch per aggregated route so
    the first instance to enable one wins and the rest skip it. Keyed by app in
    _app_registries below instead of living on app.state, so it's only ever reachable
    through this module, not through any other code holding a reference to the app.
    """

    def __init__(self) -> None:
        self.claimed_prefixes: set[str] = set()
        self.version_providers: list[Callable[[str], list[dict[str, Any]]]] = []
        self.versions_route_mounted: bool = False
        self.versions_dashboard_mounted: bool = False


_app_registries: WeakKeyDictionary[FastAPI, _AppRegistry] = WeakKeyDictionary()


def get_app_registry(app: FastAPI) -> _AppRegistry:
    registry = _app_registries.get(app)
    if registry is None:
        registry = _AppRegistry()
        _app_registries[app] = registry
    return registry


def aggregate_version_models(registry: _AppRegistry, root_path: str) -> list[dict[str, Any]]:
    version_models: list[dict[str, Any]] = []
    for provider in registry.version_providers:
        version_models.extend(provider(root_path))
    return version_models


def raise_prefix_claimed_by_self(prefix: str) -> None:
    raise RuntimeError(
        f"Prefix '{prefix}' was already claimed by this same RouterVersioner instance. "
        "This usually means prefix_format doesn't use {major}/{minor}/{version} and "
        "produces the same prefix for multiple versions, or latest_prefix collides "
        "with an already-active version prefix."
    )


def raise_prefix_claimed_by_other(prefix: str) -> None:
    raise RuntimeError(
        f"Prefix '{prefix}' is already used by another RouterVersioner attached to this app. "
        "Two RouterVersioner instances sharing the same app must use distinct "
        "prefix_format/latest_prefix values, otherwise their docs/openapi routes silently "
        "shadow each other."
    )


def check_prefix_available(app: FastAPI, prefix: str, staged_prefixes: set[str]) -> None:
    if prefix in staged_prefixes:
        raise_prefix_claimed_by_self(prefix)
    if prefix in get_app_registry(app).claimed_prefixes:
        raise_prefix_claimed_by_other(prefix)


def claim_prefix(app: FastAPI, prefix: str) -> None:
    get_app_registry(app).claimed_prefixes.add(prefix)


def add_version_provider(app: FastAPI, provider: Callable[[str], list[dict[str, Any]]]) -> None:
    get_app_registry(app).version_providers.append(provider)


def mount_versions_route(app: FastAPI, versions_route_path: str | None) -> None:
    registry = get_app_registry(app)
    if registry.versions_route_mounted:
        return
    registry.versions_route_mounted = True

    route_path = versions_route_path or "/versions"

    @app.get(route_path, tags=["Versions"], response_class=JSONResponse)
    def get_versions(request: Request) -> dict[str, Any]:
        root_path = request.scope.get("root_path", "").rstrip("/")
        return {"versions": aggregate_version_models(registry, root_path)}


def mount_versions_dashboard(
    app: FastAPI, versions_dashboard_path: str | None, hook: Callable[[list[dict[str, Any]], str], str] | None
) -> None:
    registry = get_app_registry(app)
    if registry.versions_dashboard_mounted:
        return
    registry.versions_dashboard_mounted = True

    route_path = versions_dashboard_path or "/dashboard"

    @app.get(route_path, tags=["Versions"], response_class=HTMLResponse, include_in_schema=False)
    def get_versions_dashboard(request: Request) -> HTMLResponse:
        root_path = request.scope.get("root_path", "").rstrip("/")
        models = aggregate_version_models(registry, root_path)
        if hook is not None:
            return HTMLResponse(hook(models, root_path))
        return HTMLResponse(render_versions_dashboard(models, app.title, app.version))
