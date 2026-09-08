"""Standards-based deprecation signalling: RFC 9745 Deprecation, RFC 8594 Sunset, RFC 8288 /
RFC 5829 Link relations.

Everything a deprecated route says about itself is decided here, once, at versionize() time;
the only per-request work is the route class installed by deprecation_route_class().
"""

from collections.abc import Callable
from datetime import date, datetime, timezone
from email.utils import formatdate
from typing import Any
from weakref import WeakKeyDictionary

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute

from ._compat import iter_routes_flat
from ._lifecycle import route_keys
from ._scheme import VersionScheme, version_gte
from ._versions import _ATTR_DEPRECATE_IN, _ATTR_REMOVE_IN, VersionInfo, VersionT, version_field

# dict[mounted path, header dict] stashed on the endpoint by VersionRouterBuilder._add_route and read by
# deprecation_route_class's handler; keyed by path so one endpoint can back several versions.
_ATTR_DEPRECATION_HEADERS = "_frv_deprecation_headers_by_path"


def to_epoch_seconds(value: date) -> int:
    """A datetime.date has no time or zone: pin it to midnight UTC. A datetime keeps its own
    tzinfo, or is read as UTC when naive. Used for the RFC 9745 Deprecation structured-field
    Date (@<seconds>) and, via formatdate, the RFC 8594 Sunset HTTP-date.
    """
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    else:
        moment = datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return int(moment.timestamp())


_route_classes: WeakKeyDictionary[type[APIRoute], type[APIRoute]] = WeakKeyDictionary()


def deprecation_route_class(base_route_class: type[APIRoute]) -> type[APIRoute]:
    """One subclass of base_route_class whose handler adds this package's deprecation headers
    to every response. It reads the header set off its own endpoint, keyed by the mounted path
    (stashed there by VersionRouterBuilder._add_route before mounting). Off the endpoint, not the route
    instance, because that is what survives include_router rebuilding the route onto the app:
    the endpoint object and the path carry over, a fresh instance's attributes do not.
    Subclassing keeps the base class's own get_route_handler() in the chain.

    Memoized per base class, so a custom route_class is subclassed once (its __init_subclass__
    fires once) rather than once per deprecated route. The header values are built once, at
    versionize() time; the only per-request work is expanding the "{root_path}" placeholder in
    the successor-version link (its client-visible prefix depends on root_path, a proxy/sub-app
    concern) -- the same lookup this package's docs/openapi/versions routes do.

    Deprecation/Sunset only fill a gap (setdefault): a route that set its own wins. Our Link
    value goes out as its own Link field (RFC 8288: multiple Link fields combine), so the
    route's own Link header -- one line or several -- is never read or rewritten.
    """
    cached = _route_classes.get(base_route_class)
    if cached is not None:
        return cached

    class _DeprecationHeadersRoute(base_route_class):  # type: ignore[valid-type,misc]  # ty: ignore[unsupported-base]
        def get_route_handler(self) -> Callable[[Request], Any]:
            downstream = super().get_route_handler()
            by_path: dict[str, dict[str, str]] = getattr(self.endpoint, _ATTR_DEPRECATION_HEADERS, {})
            headers = by_path.get(self.path, {})

            async def deprecation_headers_handler(request: Request) -> Response:
                response: Response = await downstream(request)
                for name, value in headers.items():
                    if "{root_path}" in value:
                        value = value.replace("{root_path}", request.scope.get("root_path", "").rstrip("/"))
                    if name == "link":
                        response.headers.append("link", value)
                    else:
                        response.headers.setdefault(name, value)
                return response

            return deprecation_headers_handler

    _route_classes[base_route_class] = _DeprecationHeadersRoute
    return _DeprecationHeadersRoute


def attach_headers(endpoint: Any, mounted_path: str, header_set: dict[str, str]) -> None:
    """Stash one path's header set on the endpoint, where the route class can still find it
    after include_router has rebuilt the route onto the app.
    """
    by_path = getattr(endpoint, _ATTR_DEPRECATION_HEADERS, None)
    if by_path is None:
        by_path = {}
        setattr(endpoint, _ATTR_DEPRECATION_HEADERS, by_path)  # noqa: B010
    by_path[mounted_path] = header_set


class DeprecationPolicy:
    """What this instance's deprecation_headers / version_info settings mean for a given route
    at a given version. Says nothing when deprecation_headers is off.
    """

    def __init__(
        self, *, enabled: bool, version_info: dict[VersionT, VersionInfo] | None, scheme: VersionScheme
    ) -> None:
        self._enabled = enabled
        self._version_info = version_info
        self._scheme = scheme

    def validate_lifecycle_dates(self, routers: list[APIRouter]) -> None:
        """Reject a route whose Sunset would precede its Deprecation: RFC 9745 forbids it.
        Only relevant when the headers are on and version_info dates both boundaries.
        """
        if not self._enabled or self._version_info is None:
            return
        for router in routers:
            for route in iter_routes_flat(router.routes):
                deprecate_in = self._scheme.extract(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
                remove_in = self._scheme.extract(route.endpoint, _ATTR_REMOVE_IN, route.path)
                if deprecate_in is None or remove_in is None:
                    continue
                deprecate_date = version_field(self._version_info, deprecate_in, "release_date")
                remove_date = version_field(self._version_info, remove_in, "release_date")
                if deprecate_date is not None and remove_date is not None and remove_date < deprecate_date:
                    raise ValueError(
                        f"version_info: remove_in {remove_in!r} ({remove_date}) is earlier than "
                        f"deprecate_in {deprecate_in!r} ({deprecate_date}) for route {route.path!r}. "
                        "RFC 9745 requires the Sunset date not to precede the Deprecation date."
                    )

    def headers_for(
        self, route: Any, version: VersionT, routes_by_version: dict[VersionT, dict[tuple[str, str], Any]]
    ) -> dict[str, str] | None:
        """The header set for one route in one version, or None when deprecation_headers is off,
        the route is not (yet) deprecated at this version, or there is nothing to say. Keys are
        lowercased. Values are final except the successor-version link, which carries a literal
        "{root_path}" token that deprecation_route_class's handler expands per request.
        """
        if not self._enabled:
            return None
        deprecate_in = self._scheme.extract(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
        if deprecate_in is None or not version_gte(version, deprecate_in):
            return None

        headers: dict[str, str] = {}

        deprecate_date = version_field(self._version_info, deprecate_in, "release_date")
        if deprecate_date is not None:
            headers["deprecation"] = f"@{to_epoch_seconds(deprecate_date)}"
        remove_in = self._scheme.extract(route.endpoint, _ATTR_REMOVE_IN, route.path)
        remove_date = version_field(self._version_info, remove_in, "release_date")
        if remove_date is not None:
            headers["sunset"] = formatdate(to_epoch_seconds(remove_date), usegmt=True)

        links: list[str] = []
        successor_prefix = self._successor_prefix(route, version, routes_by_version)
        if successor_prefix is not None:
            # {root_path} is expanded per request in deprecation_route_class's handler.
            links.append(f'<{{root_path}}{successor_prefix}{route.path}>; rel="successor-version"')
        guide = version_field(self._version_info, deprecate_in, "guide")
        if guide is not None:
            links.append(f'<{guide}>; rel="deprecation"')
        if links:
            headers["link"] = ", ".join(links)

        return headers or None

    def _successor_prefix(
        self, route: Any, version: VersionT, routes_by_version: dict[VersionT, dict[tuple[str, str], Any]]
    ) -> str | None:
        """The prefix of the first version after `version` that still serves any of this
        route's (path, method) keys. None when nothing later carries it (removed, or this is
        the last version). routes_by_version is ordered by ascending version.
        """
        keys = route_keys(route).keys()
        seen_current = False
        for candidate_version, routes_by_key in routes_by_version.items():
            if candidate_version == version:
                seen_current = True
                continue
            if not seen_current:
                continue
            if keys & routes_by_key.keys():
                return self._scheme.prefix(candidate_version)
        return None
