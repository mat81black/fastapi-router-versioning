from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from fastapi.routing import APIRoute, APIWebSocketRoute

from ._compat import iter_routes_flat, unwrap_route
from ._scheme import VersionScheme
from ._versions import _ATTR_API_VERSION, _ATTR_DEPRECATE_IN, _ATTR_REMOVE_IN, VersionT


def route_keys(route: Any) -> dict[tuple[str, str], Any]:
    path = route.path
    routes_by_key: dict[tuple[str, str], Any] = {}
    route_type = unwrap_route(route)

    if isinstance(route_type, APIRoute):
        for method in route.methods:
            routes_by_key[(path, method)] = route
    elif isinstance(route_type, APIWebSocketRoute):
        routes_by_key[(path, "")] = route

    return routes_by_key


def resolve_lifecycle(routes: list[Any], scheme: VersionScheme) -> dict[VersionT, dict[tuple[str, str], Any]]:
    """Accumulates active routes per version, honoring @api_version introduce/remove.

    Shared by collect_routes_by_version and collect_webhooks_by_version: both need the same
    introduce/remove bookkeeping, only the input route list and output shape differ.
    """
    introduced: dict[VersionT, list[Any]] = defaultdict(list)
    for route in routes:
        start_version = scheme.extract(route.endpoint, _ATTR_API_VERSION, route.path)
        introduced[start_version if start_version is not None else scheme.default_version].append(route)

    removed: dict[VersionT, list[Any]] = defaultdict(list)
    deprecated: set[VersionT] = set()
    for route in routes:
        end_version = scheme.extract(route.endpoint, _ATTR_REMOVE_IN, route.path)
        if end_version is not None:
            removed[end_version].append(route)
        deprecate_version = scheme.extract(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
        if deprecate_version is not None:
            deprecated.add(deprecate_version)

    active: dict[tuple[str, str], Any] = {}
    result: dict[VersionT, dict[tuple[str, str], Any]] = {}

    for version in sorted(set(introduced.keys()) | set(removed.keys()) | deprecated):
        for route in introduced[version]:
            active.update(route_keys(route))
        for route in removed.get(version, []):
            for route_key, keyed_route in route_keys(route).items():
                # Only remove the key if this route is still its active occupant. A newer
                # route sharing the same (path, method) may have already replaced it, in
                # which case remove_in on the superseded route must not evict the newer one.
                if active.get(route_key) is keyed_route:
                    del active[route_key]
        result[version] = dict(active)

    return result


def collect_routes_by_version(
    routers: list[APIRouter], scheme: VersionScheme
) -> dict[VersionT, dict[tuple[str, str], Any]]:
    all_routes: list[Any] = []
    for router in routers:
        all_routes.extend(iter_routes_flat(router.routes))

    return resolve_lifecycle(all_routes, scheme)


def collect_webhooks_by_version(
    webhook_routers: list[APIRouter] | None, scheme: VersionScheme
) -> dict[VersionT, list[Any]]:
    if not webhook_routers:
        return {}

    all_webhooks: list[Any] = []
    for router in webhook_routers:
        all_webhooks.extend(iter_routes_flat(router.routes))

    return {version: list(routes.values()) for version, routes in resolve_lifecycle(all_webhooks, scheme).items()}


def resolve_webhooks_for_version(
    version: VersionT, webhooks_by_version: dict[VersionT, list[Any]], app_webhooks: list[Any] | None
) -> list[Any]:
    """The webhooks one version serves. app_webhooks is the app's own webhook routes, passed
    only when webhook_routers was not configured: in that case every version inherits them
    unchanged. Otherwise the newest webhook set at or below this version wins.
    """
    if app_webhooks is not None:
        return list(app_webhooks)
    if isinstance(version, tuple):
        candidates: list[VersionT] = [v for v in webhooks_by_version if isinstance(v, tuple) and v <= version]
    else:
        candidates = [v for v in webhooks_by_version if isinstance(v, str) and v <= version]
    if not candidates:
        return []
    return webhooks_by_version[max(candidates)]
