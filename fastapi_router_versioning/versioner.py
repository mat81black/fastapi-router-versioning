import inspect

from collections import defaultdict
from collections.abc import Callable, Iterator
from enum import Enum
from typing import Any, TypeAlias, TypeVar

import fastapi.openapi.utils
import fastapi.routing

from fastapi import APIRouter, FastAPI, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute, APIWebSocketRoute

# iter_route_contexts was introduced in FastAPI 0.137.2. On older versions the
# attribute does not exist and getattr returns None, activating the fallback path.
_route_contexts_fn: Callable[..., Any] | None = getattr(fastapi.routing, "iter_route_contexts", None)


CallableT = TypeVar("CallableT", bound=Callable[..., Any])

VersionT: TypeAlias = tuple[int, int] | str
_OpenAPICacheKey: TypeAlias = tuple[VersionT, str]

_ATTR_API_VERSION = "_api_version"
_ATTR_DEPRECATE_IN = "_deprecate_in_version"
_ATTR_REMOVE_IN = "_remove_in_version"


class VersionFormat(str, Enum):
    """
    Defines the allowed versioning strategy for the RouterVersioner.
    """

    SEMVER = "semver"  # Accepts tuple[int, int] (e.g., (1, 0))
    CALVER = "calver"  # Accepts str (e.g., "2025-01-01", "v1")


def _validate_api_version_arg(value: Any, param_name: str) -> None:
    if not isinstance(value, (tuple, str)):
        raise TypeError(
            f"api_version: '{param_name}' must be a tuple[int, int] (SemVer) or str (CalVer), "
            f"got {type(value).__name__!r} instead. "
            "Example: @api_version((1, 0)) or @api_version('2025-01-01')."
        )


def api_version(
    version: VersionT,
    *,
    deprecate_in: VersionT | None = None,
    remove_in: VersionT | None = None,
) -> Callable[[CallableT], CallableT]:
    """
    Decorator to annotate API routes with their specific version.

    Accepts both Semantic Versioning (e.g., tuple (1, 0)) and Calendar Versioning
    or strings (e.g., "2025-01-01", "v1").
    Metadata is injected directly into the wrapper function, allowing the
    RouterVersioner to organize the routes dynamically.
    """
    _validate_api_version_arg(version, "version")
    if deprecate_in is not None:
        _validate_api_version_arg(deprecate_in, "deprecate_in")
    if remove_in is not None:
        _validate_api_version_arg(remove_in, "remove_in")

    def decorator(func: CallableT) -> CallableT:
        setattr(func, _ATTR_API_VERSION, version)  # noqa: B010

        if deprecate_in is not None:
            setattr(func, _ATTR_DEPRECATE_IN, deprecate_in)  # noqa: B010

        if remove_in is not None:
            setattr(func, _ATTR_REMOVE_IN, remove_in)  # noqa: B010

        return func

    return decorator


class RouterVersioner:
    def __init__(
        self,
        app: FastAPI,
        routers: list[APIRouter] | APIRouter,
        version_format: VersionFormat = VersionFormat.SEMVER,
        prefix_format: str | None = None,
        semantic_version_format: str | None = None,
        default_version: VersionT | None = None,
        latest_prefix: str | None = None,
        include_version_docs: bool = True,
        include_version_openapi_route: bool = True,
        include_versions_route: bool = False,
        sort_routes: bool = False,
        callback: Callable[[APIRouter, VersionT, str], None] | None = None,
        webhook_routers: list[APIRouter] | APIRouter | None = None,
        openapi_hook: Callable[[dict[str, Any], VersionT], dict[str, Any]] | None = None,
        swagger_js_url: str | None = None,
        swagger_css_url: str | None = None,
        swagger_favicon_url: str | None = None,
        redoc_js_url: str | None = None,
        redoc_favicon_url: str | None = None,
        redoc_with_google_fonts: bool = True,
    ):
        """
        Versionize your FastAPI application in-place, organizing routes based on their API version.

        :param app: The main FastAPI application instance.
        :param routers: A single APIRouter or a list of APIRouters containing the routes to version.
        :param version_format: Enforces the versioning strategy (SEMVER or CALVER).
            For CALVER, version strings must be lexicographically sortable in the intended
            order (e.g. ISO dates "2025-01-01", zero-padded numbers "v01", "v02").
            Strings like "v1", "v10", "v2" will NOT sort correctly and cause routes to
            appear in the wrong versions.
        :param prefix_format: Format used to build the route prefix.
        :param semantic_version_format: Format used to build the version in Swagger/ReDoc.
        :param default_version: Default version used if a route is not explicitly decorated.
        :param latest_prefix: If specified, creates an alias prefix for the latest active version.
        :param include_version_docs: If True, creates isolated Swagger/ReDoc pages for each version.
        :param include_version_openapi_route: If True, creates an independent openapi.json route for each version.
        :param include_versions_route: If True, adds a 'GET /versions' endpoint returning info on all active API versions.
        :param sort_routes: If True, sorts all routes alphabetically by path.
        :param callback: Optional hook invoked every time a versioned APIRouter is created.
        :param webhook_routers: A single APIRouter or a list of APIRouters containing webhook definitions
            annotated with @api_version. When provided, each version's OpenAPI schema shows only the
            webhooks active in that version (using the same introduce/remove lifecycle as regular routes).
            When None, every version inherits app.webhooks unchanged.
        :param openapi_hook: Optional hook applied to the generated OpenAPI schema for each version.
            Receives the schema dict and the current version; must return the (modified) schema dict.
            Use this to add custom extensions, logos, or version-specific metadata that would
            otherwise be bypassed by the per-version schema generation.
        :param swagger_js_url: Custom URL for the Swagger UI JS bundle. Defaults to FastAPI's CDN URL.
        :param swagger_css_url: Custom URL for the Swagger UI CSS. Defaults to FastAPI's CDN URL.
        :param swagger_favicon_url: Custom URL for the Swagger UI favicon. Defaults to FastAPI's favicon.
        :param redoc_js_url: Custom URL for the ReDoc JS bundle. Defaults to FastAPI's CDN URL.
        :param redoc_favicon_url: Custom URL for the ReDoc favicon. Defaults to FastAPI's favicon.
        :param redoc_with_google_fonts: If False, ReDoc will not load Google Fonts. Defaults to True.
        """
        self._app = app
        self._routers = [routers] if isinstance(routers, APIRouter) else routers
        self._version_format = version_format

        if prefix_format is None:
            self._prefix_format = "/v{major}_{minor}" if version_format == VersionFormat.SEMVER else "/{version}"
        else:
            self._prefix_format = prefix_format

        if semantic_version_format is None:
            self._semantic_version_format = "{major}.{minor}" if version_format == VersionFormat.SEMVER else "{version}"
        else:
            self._semantic_version_format = semantic_version_format

        self._latest_prefix = latest_prefix
        self._include_version_docs = include_version_docs
        self._include_version_openapi_route = include_version_openapi_route
        self._include_versions_route = include_versions_route
        self._sort_routes = sort_routes
        self._callback = callback
        self._webhook_routers: list[APIRouter] | None = (
            [webhook_routers] if isinstance(webhook_routers, APIRouter) else webhook_routers
        )
        self._openapi_hook = openapi_hook
        self._swagger_js_url = swagger_js_url
        self._swagger_css_url = swagger_css_url
        self._swagger_favicon_url = swagger_favicon_url
        self._redoc_js_url = redoc_js_url
        self._redoc_favicon_url = redoc_favicon_url
        self._redoc_with_google_fonts = redoc_with_google_fonts
        self._openapi_schemas_cache: dict[_OpenAPICacheKey, dict[str, Any]] = {}
        self._openapi_routes_versions: dict[_OpenAPICacheKey, int | None] = {}

        if default_version is None:
            self._default_version: VersionT = (1, 0) if version_format == VersionFormat.SEMVER else "1"
        else:
            self._validate_version_type(default_version, "default_version fallback")
            self._default_version = default_version

        self._docs_url = getattr(app, "docs_url", "/docs")
        self._redoc_url = getattr(app, "redoc_url", "/redoc")

        self._versionized = False

    def _validate_version_type(self, version: Any, route_path: str) -> None:
        if self._version_format == VersionFormat.SEMVER:
            if not isinstance(version, tuple) or len(version) != 2 or not all(isinstance(i, int) for i in version):
                error_msg = f"RouterVersioner expects SEMVER, but found an invalid version '{version}' on {route_path}. Use a tuple of exactly two integers: (major, minor). e.g., (1, 0)."
                raise ValueError(error_msg)
        elif self._version_format == VersionFormat.CALVER:
            if not isinstance(version, str):
                error_msg = f"RouterVersioner expects CALVER, but found a non-string version '{version}' on {route_path}. Use a string like '2025-01-01'."
                raise ValueError(error_msg)

    @staticmethod
    def _format_string(format_str: str, version: VersionT) -> str:
        if isinstance(version, tuple):
            return format_str.format(major=version[0], minor=version[1], version=f"{version[0]}_{version[1]}")
        return format_str.format(version=version, major=version, minor=version)

    @staticmethod
    def _version_gte(a: VersionT, b: VersionT) -> bool:
        if isinstance(a, tuple) and isinstance(b, tuple):
            return a >= b
        if isinstance(a, str) and isinstance(b, str):
            return a >= b
        return False

    @staticmethod
    def _iter_routes_flat(routes: list[Any]) -> Iterator[Any]:
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

    @staticmethod
    def _unwrap_route(route: Any) -> Any:
        # RouteContext (FastAPI >= 0.137.2) wraps the original route.
        # Attributes like response_model, status_code, operation_id live on the original.
        return getattr(route, "original_route", route)

    def _extract_version_attribute(self, endpoint: Any, attribute: str, route_path: str) -> VersionT | None:
        val = getattr(endpoint, attribute, None)
        if isinstance(val, (tuple, str)):
            self._validate_version_type(val, route_path)
            return val
        return None

    def versionize(self) -> list[VersionT]:
        """
        Reads the configured routers, groups their routes by version, and mounts one
        versioned router per active version on the app.

        May only be called once per instance. If it raises, the app failed to load: don't
        catch the exception and retry, since some versions may already be mounted and this
        package makes no attempt to undo that.

        :return: The list of versions that were actually mounted.
        """
        if self._versionized:
            raise RuntimeError(
                "versionize() was already called on this RouterVersioner instance. "
                "Create a new RouterVersioner if you need to versionize a router again."
            )
        self._versionized = True

        routes_by_version = self._get_routes_by_version()
        versions = list(routes_by_version.keys())
        webhooks_by_version = self._get_webhooks_by_version()

        prepared: list[tuple[str, APIRouter]] = []
        staged_prefixes: set[str] = set()
        latest_version: VersionT | None = None
        latest_routes: dict[tuple[str, str], Any] = {}
        latest_webhooks: list[Any] = []

        for version, routes_by_key in routes_by_version.items():
            version_prefix = self._format_string(self._prefix_format, version)
            self._check_prefix_available(version_prefix, staged_prefixes)
            staged_prefixes.add(version_prefix)

            active_webhooks = self._resolve_webhooks_for_version(version, webhooks_by_version)
            version_router = self._build_version_router(
                version=version, version_prefix=version_prefix, routes_by_key=routes_by_key, webhooks=active_webhooks
            )
            if self._callback:
                self._callback(version_router, version, version_prefix)

            prepared.append((version_prefix, version_router))
            latest_version = version
            latest_routes = routes_by_key
            latest_webhooks = active_webhooks

        if self._latest_prefix is not None and latest_version is not None:
            self._check_prefix_available(self._latest_prefix, staged_prefixes)
            staged_prefixes.add(self._latest_prefix)

            latest_router = self._build_version_router(
                version=latest_version,
                version_prefix=self._latest_prefix,
                routes_by_key=latest_routes,
                webhooks=latest_webhooks,
            )
            if self._callback:
                self._callback(latest_router, latest_version, self._latest_prefix)
            prepared.append((self._latest_prefix, latest_router))

        for prefix, _router in prepared:
            self._claim_prefix(prefix)
        for _prefix, router in prepared:
            self._app.include_router(router=router)
        if self._include_versions_route:
            self._add_versions_route(versions=versions)

        return versions

    @classmethod
    def _get_route_keys(cls, route: Any) -> dict[tuple[str, str], Any]:
        path = route.path
        routes_by_key: dict[tuple[str, str], Any] = {}
        route_type = cls._unwrap_route(route)

        if isinstance(route_type, APIRoute):
            for method in route.methods:
                routes_by_key[(path, method)] = route
        elif isinstance(route_type, APIWebSocketRoute):
            routes_by_key[(path, "")] = route

        return routes_by_key

    def _resolve_lifecycle(self, routes: list[Any]) -> dict[VersionT, dict[tuple[str, str], Any]]:
        """Accumulates active routes per version, honoring @api_version introduce/remove.

        Shared by _get_routes_by_version and _get_webhooks_by_version: both need the same
        introduce/remove bookkeeping, only the input route list and output shape differ.
        """
        introduced: dict[VersionT, list[Any]] = defaultdict(list)
        for route in routes:
            start_version = self._extract_version_attribute(route.endpoint, _ATTR_API_VERSION, route.path)
            introduced[start_version if start_version is not None else self._default_version].append(route)

        removed: dict[VersionT, list[Any]] = defaultdict(list)
        deprecated: set[VersionT] = set()
        for route in routes:
            end_version = self._extract_version_attribute(route.endpoint, _ATTR_REMOVE_IN, route.path)
            if end_version is not None:
                removed[end_version].append(route)
            deprecate_version = self._extract_version_attribute(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
            if deprecate_version is not None:
                deprecated.add(deprecate_version)

        active: dict[tuple[str, str], Any] = {}
        result: dict[VersionT, dict[tuple[str, str], Any]] = {}

        for version in sorted(set(introduced.keys()) | set(removed.keys()) | deprecated):
            for route in introduced[version]:
                active.update(self._get_route_keys(route=route))
            for route in removed.get(version, []):
                for route_key, keyed_route in self._get_route_keys(route=route).items():
                    # Only remove the key if this route is still its active occupant. A newer
                    # route sharing the same (path, method) may have already replaced it, in
                    # which case remove_in on the superseded route must not evict the newer one.
                    if active.get(route_key) is keyed_route:
                        del active[route_key]
            result[version] = dict(active)

        return result

    def _get_routes_by_version(self) -> dict[VersionT, dict[tuple[str, str], Any]]:
        all_routes: list[Any] = []
        for router in self._routers:
            all_routes.extend(self._iter_routes_flat(router.routes))

        return self._resolve_lifecycle(all_routes)

    def _get_webhooks_by_version(self) -> dict[VersionT, list[Any]]:
        if not self._webhook_routers:
            return {}

        all_webhooks: list[Any] = []
        for router in self._webhook_routers:
            all_webhooks.extend(self._iter_routes_flat(router.routes))

        return {version: list(routes.values()) for version, routes in self._resolve_lifecycle(all_webhooks).items()}

    @staticmethod
    def _raise_prefix_claimed_by_self(prefix: str) -> None:
        raise RuntimeError(
            f"Prefix '{prefix}' was already claimed by this same RouterVersioner instance. "
            "This usually means prefix_format doesn't use {major}/{minor}/{version} and "
            "produces the same prefix for multiple versions, or latest_prefix collides "
            "with an already-active version prefix."
        )

    @staticmethod
    def _raise_prefix_claimed_by_other(prefix: str) -> None:
        raise RuntimeError(
            f"Prefix '{prefix}' is already used by another RouterVersioner attached to this app. "
            "Two RouterVersioner instances sharing the same app must use distinct "
            "prefix_format/latest_prefix values, otherwise their docs/openapi routes silently "
            "shadow each other."
        )

    def _check_prefix_available(self, prefix: str, staged_prefixes: set[str]) -> None:
        if prefix in staged_prefixes:
            self._raise_prefix_claimed_by_self(prefix)
        claimed: set[str] | None = getattr(self._app.state, "_router_versioner_claimed_prefixes", None)
        if claimed is not None and prefix in claimed:
            self._raise_prefix_claimed_by_other(prefix)

    def _claim_prefix(self, prefix: str) -> None:
        claimed: set[str] | None = getattr(self._app.state, "_router_versioner_claimed_prefixes", None)
        if claimed is None:
            claimed = set()
            self._app.state._router_versioner_claimed_prefixes = claimed
        claimed.add(prefix)

    def _resolve_webhooks_for_version(
        self, version: VersionT, webhooks_by_version: dict[VersionT, list[Any]]
    ) -> list[Any]:
        if not webhooks_by_version:
            # webhook_routers not provided: fall back to global app.webhooks
            return list(self._app.webhooks.routes)
        if isinstance(version, tuple):
            candidates: list[VersionT] = [v for v in webhooks_by_version if isinstance(v, tuple) and v <= version]
        else:
            candidates = [v for v in webhooks_by_version if isinstance(v, str) and v <= version]
        if not candidates:
            return []
        return webhooks_by_version[max(candidates)]

    def _build_version_router(
        self,
        version: VersionT,
        version_prefix: str,
        routes_by_key: dict[tuple[str, str], Any],
        webhooks: list[Any],
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
            self._add_route_to_router(
                route=route, router=router, version=version, active_methods=active_methods or None
            )

        self._add_version_docs(router=router, version=version, version_prefix=version_prefix, webhooks=webhooks)

        return router

    def _add_route_to_router(
        self, route: Any, router: APIRouter, version: VersionT, active_methods: set[str] | None = None
    ) -> None:
        # Read attributes from the original route, not the RouteContext proxy. The proxy
        # (FastAPI >= 0.137.2) only merges path/tags/deps; other fields such as
        # response_model, status_code, and operation_id would be silently lost.
        source_route = self._unwrap_route(route)
        add_method: Callable[..., Any]

        if isinstance(source_route, APIRoute):
            add_method = router.add_api_route
        elif isinstance(source_route, APIWebSocketRoute):
            add_method = router.add_api_websocket_route
        else:
            raise TypeError(f"Unsupported route type: {type(source_route).__name__}")

        valid_params = inspect.signature(add_method).parameters.keys()
        filtered_kwargs = {k: getattr(source_route, k) for k in valid_params if hasattr(source_route, k)}
        filtered_kwargs.setdefault("endpoint", source_route.endpoint)
        # Override path/tags/deps with the merged values from RouteContext when present.
        for merged_attr in ("path", "tags", "dependencies"):
            if hasattr(route, merged_attr) and merged_attr in valid_params:
                filtered_kwargs[merged_attr] = getattr(route, merged_attr)
        # A sibling route may have taken over some of this route's original methods at this
        # version: mount only the methods still assigned to it, not its full original set.
        if active_methods is not None and "methods" in valid_params:
            filtered_kwargs["methods"] = active_methods

        deprecated_in_version = self._extract_version_attribute(route.endpoint, _ATTR_DEPRECATE_IN, route.path)
        if deprecated_in_version is not None and self._version_gte(version, deprecated_in_version):
            filtered_kwargs["deprecated"] = True

        # An empty string name causes an internal FastAPI error; drop it to use the default.
        if "name" in filtered_kwargs and not filtered_kwargs["name"]:
            filtered_kwargs.pop("name")

        add_method(**filtered_kwargs)

    def _add_version_docs(self, router: APIRouter, version: VersionT, version_prefix: str, webhooks: list[Any]) -> None:
        doc_version_str = self._format_string(self._semantic_version_format, version)
        title = f"{self._app.title} - v{doc_version_str}"
        versioned_tags = self._collect_versioned_tags(router)
        openapi_url = self._app.openapi_url

        if self._include_version_openapi_route and openapi_url is not None:
            self._add_openapi_route(
                router, title, doc_version_str, versioned_tags, openapi_url, version, version_prefix, webhooks
            )

        if (
            self._include_version_docs
            and self._include_version_openapi_route
            and self._docs_url is not None
            and openapi_url is not None
        ):
            self._add_swagger_ui_routes(router, title, version_prefix, self._docs_url, openapi_url)

        if (
            self._include_version_docs
            and self._include_version_openapi_route
            and self._redoc_url is not None
            and openapi_url is not None
        ):
            self._add_redoc_route(router, title, version_prefix, self._redoc_url, openapi_url)

    def _collect_versioned_tags(self, router: APIRouter) -> list[dict[str, Any]]:
        if self._app.openapi_tags is None:
            return []
        tags: set[str | Enum] = set()
        for route in router.routes:
            if isinstance(route, APIRoute) and isinstance(route.tags, list):
                tags.update(route.tags)
        if not tags:
            return []
        return [tag for tag in self._app.openapi_tags if tag["name"] in tags]

    def _add_openapi_route(
        self,
        router: APIRouter,
        title: str,
        doc_version_str: str,
        versioned_tags: list[dict[str, Any]],
        openapi_url: str,
        version: VersionT,
        version_prefix: str,
        webhooks: list[Any],
    ) -> None:
        cache_key: _OpenAPICacheKey = (version, version_prefix)

        @router.get(openapi_url, include_in_schema=False)
        async def get_openapi(req: Request) -> Any:
            # _get_routes_version() is the same internal FastAPI uses for its own schema cache;
            # if unavailable (private API removed), current_routes_version stays None and the
            # cache persists indefinitely — degraded but correct.
            _get_routes_version = getattr(router, "_get_routes_version", None)
            current_routes_version = _get_routes_version() if _get_routes_version else None

            cached = self._openapi_schemas_cache.get(cache_key)
            if cached is None or self._openapi_routes_versions.get(cache_key) != current_routes_version:
                schema = fastapi.openapi.utils.get_openapi(
                    title=title,
                    version=doc_version_str,
                    openapi_version=self._app.openapi_version,
                    summary=self._app.summary,
                    description=self._app.description,
                    routes=router.routes,
                    webhooks=webhooks,
                    tags=versioned_tags,
                    servers=self._app.servers,
                    terms_of_service=self._app.terms_of_service,
                    contact=self._app.contact,
                    license_info=self._app.license_info,
                    separate_input_output_schemas=self._app.separate_input_output_schemas,
                    external_docs=self._app.openapi_external_docs,
                )

                if self._openapi_hook is not None:
                    schema = self._openapi_hook(schema, version)
                self._openapi_schemas_cache[cache_key] = schema
                self._openapi_routes_versions[cache_key] = current_routes_version
            else:
                schema = self._openapi_schemas_cache[cache_key]

            # root_path is per-request: shallow copy to avoid polluting the cache
            root_path = req.scope.get("root_path", "").rstrip("/")
            if root_path and getattr(self._app, "root_path_in_servers", True):
                server_urls = {s.get("url") for s in schema.get("servers", [])}
                if root_path not in server_urls:
                    schema = dict(schema)
                    schema["servers"] = [{"url": root_path}] + schema.get("servers", [])

            return schema

    def _add_swagger_ui_routes(
        self, router: APIRouter, title: str, version_prefix: str, docs_url: str, openapi_url: str
    ) -> None:
        swagger_asset_kwargs: dict[str, Any] = {}
        if self._swagger_js_url is not None:
            swagger_asset_kwargs["swagger_js_url"] = self._swagger_js_url
        if self._swagger_css_url is not None:
            swagger_asset_kwargs["swagger_css_url"] = self._swagger_css_url
        if self._swagger_favicon_url is not None:
            swagger_asset_kwargs["swagger_favicon_url"] = self._swagger_favicon_url

        # root_path is resolved at request time (mirrors FastAPI's own /docs handler).
        @router.get(docs_url, include_in_schema=False)
        async def get_docs(request: Request) -> HTMLResponse:
            root_path = request.scope.get("root_path", "").rstrip("/")
            versioned_openapi_url = f"{root_path}{version_prefix}{openapi_url}"
            oauth2_redirect_url = (
                f"{root_path}{version_prefix}{self._app.swagger_ui_oauth2_redirect_url}"
                if self._app.swagger_ui_oauth2_redirect_url
                else None
            )
            return get_swagger_ui_html(
                openapi_url=versioned_openapi_url,
                title=title,
                oauth2_redirect_url=oauth2_redirect_url,
                init_oauth=self._app.swagger_ui_init_oauth,
                swagger_ui_parameters=self._app.swagger_ui_parameters,
                **swagger_asset_kwargs,
            )

        if self._app.swagger_ui_oauth2_redirect_url:

            @router.get(self._app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
            async def get_oauth2_redirect(_request: Request) -> HTMLResponse:
                return get_swagger_ui_oauth2_redirect_html()

    def _add_redoc_route(
        self, router: APIRouter, title: str, version_prefix: str, redoc_url: str, openapi_url: str
    ) -> None:
        redoc_asset_kwargs: dict[str, Any] = {"with_google_fonts": self._redoc_with_google_fonts}
        if self._redoc_js_url is not None:
            redoc_asset_kwargs["redoc_js_url"] = self._redoc_js_url
        if self._redoc_favicon_url is not None:
            redoc_asset_kwargs["redoc_favicon_url"] = self._redoc_favicon_url

        @router.get(redoc_url, include_in_schema=False)
        async def get_redoc(request: Request) -> HTMLResponse:
            root_path = request.scope.get("root_path", "").rstrip("/")
            versioned_openapi_url = f"{root_path}{version_prefix}{openapi_url}"
            return get_redoc_html(openapi_url=versioned_openapi_url, title=title, **redoc_asset_kwargs)

    def _build_version_models(self, versions: list[VersionT], root_path: str) -> list[dict[str, Any]]:
        version_models: list[dict[str, Any]] = []
        for version in versions:
            version_prefix = self._format_string(self._prefix_format, version)
            doc_version_str = self._format_string(self._semantic_version_format, version)

            version_model = {"version": doc_version_str}

            if self._include_version_openapi_route and self._app.openapi_url is not None:
                version_model["openapi_url"] = f"{root_path}{version_prefix}{self._app.openapi_url}"
            if self._include_version_docs and self._include_version_openapi_route and self._docs_url is not None:
                version_model["swagger_url"] = f"{root_path}{version_prefix}{self._docs_url}"
            if self._include_version_docs and self._include_version_openapi_route and self._redoc_url is not None:
                version_model["redoc_url"] = f"{root_path}{version_prefix}{self._redoc_url}"

            version_models.append(version_model)

        return version_models

    def _add_versions_route(self, versions: list[VersionT]) -> None:
        providers: list[Callable[[str], list[dict[str, Any]]]] | None = getattr(
            self._app.state, "_router_versioner_version_providers", None
        )
        is_first_provider = providers is None
        if providers is None:
            providers = []
            self._app.state._router_versioner_version_providers = providers
        providers.append(lambda root_path: self._build_version_models(versions, root_path))

        if not is_first_provider:
            return

        @self._app.get("/versions", tags=["Versions"], response_class=JSONResponse)
        def get_versions(request: Request) -> dict[str, Any]:
            root_path = request.scope.get("root_path", "").rstrip("/")
            version_models: list[dict[str, Any]] = []
            for provider in providers:
                version_models.extend(provider(root_path))
            return {"versions": version_models}
