import inspect

from collections import defaultdict
from collections.abc import Callable, Iterator
from enum import Enum
from typing import Any, TypeAlias, TypeVar

import fastapi.openapi.utils

from fastapi import APIRouter, FastAPI
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.requests import Request

try:
    from fastapi.routing import iter_route_contexts

    FASTAPI_SUPPORTS_ROUTE_CONTEXTS = True
except ImportError:  # pragma: no cover
    FASTAPI_SUPPORTS_ROUTE_CONTEXTS = False  # pragma: no cover


def _iter_routes_flat(routes: list[Any]) -> Iterator[Any]:
    """
    Flattens the route tree using iter_route_contexts (FastAPI >= 0.137.2),
    or yields the original flat list for older versions.
    """
    if not FASTAPI_SUPPORTS_ROUTE_CONTEXTS:  # pragma: no cover
        yield from routes  # pragma: no cover
        return  # pragma: no cover

    for route_ctx in iter_route_contexts(routes):
        original = route_ctx.original_route
        if isinstance(original, APIRoute):
            # RouteContext merges path/tags/deps via __getattr__; use the context directly.
            yield route_ctx
        else:
            yield original


CallableT = TypeVar("CallableT", bound=Callable[..., Any])

VersionT: TypeAlias = tuple[int, int] | str


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
        setattr(func, "_api_version", version)  # noqa: B010

        if deprecate_in is not None:
            setattr(func, "_deprecate_in_version", deprecate_in)  # noqa: B010

        if remove_in is not None:
            setattr(func, "_remove_in_version", remove_in)  # noqa: B010

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
    ):
        """
        Versionize your FastAPI application in-place, organizing routes based on their API version.

        :param app: The main FastAPI application instance.
        :param routers: A single APIRouter or a list of APIRouters containing the routes to version.
        :param version_format: Enforces the versioning strategy (SEMVER or CALVER).
        :param prefix_format: Format used to build the route prefix.
        :param semantic_version_format: Format used to build the version in Swagger/ReDoc.
        :param default_version: Default version used if a route is not explicitly decorated.
        :param latest_prefix: If specified, creates an alias prefix for the latest active version.
        :param include_version_docs: If True, creates isolated Swagger/ReDoc pages for each version.
        :param include_version_openapi_route: If True, creates an independent openapi.json route for each version.
        :param include_versions_route: If True, adds a 'GET /versions' endpoint returning info on all active API versions.
        :param sort_routes: If True, sorts all routes alphabetically by path.
        :param callback: Optional hook invoked every time a versioned APIRouter is created.
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

        if default_version is None:
            self._default_version: VersionT = (1, 0) if version_format == VersionFormat.SEMVER else "1"
        else:
            self._validate_version_type(default_version, "default_version fallback")
            self._default_version = default_version

        self._docs_url = getattr(app, "docs_url", "/docs")
        self._redoc_url = getattr(app, "redoc_url", "/redoc")

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

    def _extract_version_attribute(self, endpoint: Any, attribute: str, route_path: str) -> VersionT | None:
        val = getattr(endpoint, attribute, None)
        if isinstance(val, (tuple, str)):
            self._validate_version_type(val, route_path)
            return val
        return None

    def versionize(self) -> list[VersionT]:
        version, routes_by_key = None, None
        routes_by_version = self._get_routes_by_version()
        versions = list(routes_by_version.keys())

        for version, routes_by_key in routes_by_version.items():
            version_prefix = self._format_string(self._prefix_format, version)

            version_router = self._build_version_router(
                version=version, version_prefix=version_prefix, routes_by_key=routes_by_key
            )

            if self._callback:
                self._callback(version_router, version, version_prefix)

            self._app.include_router(router=version_router)

        if self._latest_prefix is not None and routes_by_key and version is not None:
            latest_router = self._build_version_router(
                version=version, version_prefix=self._latest_prefix, routes_by_key=routes_by_key
            )
            if self._callback:
                self._callback(latest_router, version, self._latest_prefix)
            self._app.include_router(router=latest_router)

        if self._include_versions_route:
            self._add_versions_route(versions=versions)

        return versions

    def _build_api_url(self, version_prefix: str, path: str) -> str:
        root_path = (self._app.root_path or "").rstrip("/")
        return f"{root_path}{version_prefix}{path}"

    def _build_version_router(
        self,
        version: VersionT,
        version_prefix: str,
        routes_by_key: dict[tuple[str, str], Any],
    ) -> APIRouter:
        router = APIRouter(prefix=version_prefix, responses=self._app.router.responses)

        if self._sort_routes:
            # Natural sort by path (Python dict insertion order is preserved)
            routes_by_key = dict(sorted(routes_by_key.items()))

        for route in routes_by_key.values():
            self._add_route_to_router(route=route, router=router, version=version)

        self._add_version_docs(router=router, version=version, version_prefix=version_prefix)

        return router

    def _get_routes_by_version(
        self,
    ) -> dict[VersionT, dict[tuple[str, str], Any]]:
        all_routes: list[Any] = []
        for router in self._routers:
            all_routes.extend(_iter_routes_flat(router.routes))

        routes_by_start_version: dict[VersionT, list[Any]] = defaultdict(list)
        for route in all_routes:
            start_version = self._extract_version_attribute(route.endpoint, "_api_version", route.path)
            if start_version is None:
                start_version = self._default_version
            routes_by_start_version[start_version].append(route)

        routes_by_end_version: dict[VersionT, list[Any]] = defaultdict(list)
        for route in all_routes:
            end_version = self._extract_version_attribute(route.endpoint, "_remove_in_version", route.path)
            if end_version is not None:
                routes_by_end_version[end_version].append(route)

        all_version_keys = set(routes_by_start_version.keys()) | set(routes_by_end_version.keys())
        versions = sorted(all_version_keys)
        routes_by_version: dict[VersionT, dict[tuple[str, str], Any]] = {}
        curr_version_routes_by_key: dict[tuple[str, str], Any] = {}

        for version in versions:
            for route in routes_by_start_version[version]:
                route_keys = self._get_route_keys(route=route)
                curr_version_routes_by_key.update(route_keys)

            for route in routes_by_end_version.get(version, []):
                route_keys = self._get_route_keys(route=route)
                for route_key in route_keys:
                    curr_version_routes_by_key.pop(route_key, None)

            routes_by_version[version] = dict(curr_version_routes_by_key)

        return routes_by_version

    @classmethod
    def _get_route_keys(cls, route: Any) -> dict[tuple[str, str], Any]:
        path = route.path
        routes_by_key: dict[tuple[str, str], Any] = {}

        # Unwrap the original route, bypassing the RouteContext proxy (FastAPI >= 0.137.2).
        route_type = getattr(route, "original_route", route)

        if isinstance(route_type, APIRoute):
            for method in route.methods:
                routes_by_key[(path, method)] = route
        elif isinstance(route_type, APIWebSocketRoute):
            routes_by_key[(path, "")] = route

        return routes_by_key

    def _add_version_docs(self, router: APIRouter, version: VersionT, version_prefix: str) -> None:
        doc_version_str = self._format_string(self._semantic_version_format, version)
        title = f"{self._app.title} - v{doc_version_str}"
        tags: set[str | Enum] = set()
        versioned_tags: list[dict[str, Any]] = []

        if self._app.openapi_tags is not None:
            for route in router.routes:
                if isinstance(route, APIRoute) and isinstance(route.tags, list):
                    tags.update(route.tags)

            if tags:
                openapi_tags = self._app.openapi_tags or []
                for openapi_tag in openapi_tags:
                    if openapi_tag["name"] in tags:
                        versioned_tags.append(openapi_tag)

        # 1. Independent OpenAPI JSON Route
        if self._include_version_openapi_route and self._app.openapi_url is not None:

            @router.get(self._app.openapi_url, include_in_schema=False)
            async def get_openapi(req: Request) -> Any:
                schema = fastapi.openapi.utils.get_openapi(
                    title=title,
                    version=doc_version_str,
                    openapi_version=self._app.openapi_version,
                    summary=self._app.summary,
                    description=self._app.description,
                    terms_of_service=self._app.terms_of_service,
                    contact=self._app.contact,
                    license_info=self._app.license_info,
                    routes=router.routes,
                    webhooks=self._app.webhooks.routes,
                    tags=versioned_tags,
                    servers=self._app.servers,
                    separate_input_output_schemas=self._app.separate_input_output_schemas,
                )

                root_path = req.scope.get("root_path", "").rstrip("/")
                if root_path and getattr(self._app, "root_path_in_servers", True):
                    server_urls = {s.get("url") for s in schema.get("servers", [])}
                    if root_path not in server_urls:
                        schema = dict(schema)
                        schema["servers"] = [{"url": root_path}] + schema.get("servers", [])

                return schema

        # 2. Independent Swagger UI Route
        if self._include_version_docs and self._docs_url is not None and self._app.openapi_url is not None:
            versioned_openapi_url = self._build_api_url(version_prefix, self._app.openapi_url)
            versioned_oauth2_redirect_url = (
                self._build_api_url(version_prefix, self._app.swagger_ui_oauth2_redirect_url)
                if self._app.swagger_ui_oauth2_redirect_url
                else None
            )

            @router.get(self._docs_url, include_in_schema=False)
            async def get_docs(_request: Request) -> HTMLResponse:
                return get_swagger_ui_html(
                    openapi_url=versioned_openapi_url,
                    title=title,
                    oauth2_redirect_url=versioned_oauth2_redirect_url,
                )

            if self._app.swagger_ui_oauth2_redirect_url:

                @router.get(self._app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
                async def get_oauth2_redirect(_request: Request) -> HTMLResponse:
                    return get_swagger_ui_oauth2_redirect_html()

        # 3. Independent ReDoc Route
        if self._include_version_docs and self._redoc_url is not None and self._app.openapi_url is not None:
            versioned_openapi_url_redoc = self._build_api_url(version_prefix, self._app.openapi_url)

            @router.get(self._redoc_url, include_in_schema=False)
            async def get_redoc(_request: Request) -> HTMLResponse:
                return get_redoc_html(openapi_url=versioned_openapi_url_redoc, title=title)

    def _add_versions_route(self, versions: list[VersionT]) -> None:
        @self._app.get("/versions", tags=["Versions"], response_class=JSONResponse)
        def get_versions() -> dict[str, Any]:
            version_models: list[dict[str, Any]] = []
            for version in versions:
                version_prefix = self._format_string(self._prefix_format, version)
                doc_version_str = self._format_string(self._semantic_version_format, version)

                version_model = {"version": doc_version_str}

                if self._include_version_openapi_route and self._app.openapi_url is not None:
                    version_model["openapi_url"] = self._build_api_url(version_prefix, self._app.openapi_url)
                if self._include_version_docs and self._docs_url is not None:
                    version_model["swagger_url"] = self._build_api_url(version_prefix, self._docs_url)
                if self._include_version_docs and self._redoc_url is not None:
                    version_model["redoc_url"] = self._build_api_url(version_prefix, self._redoc_url)

                version_models.append(version_model)

            return {"versions": version_models}

    def _add_route_to_router(self, route: Any, router: APIRouter, version: VersionT) -> None:
        route_type = getattr(route, "original_route", route)
        add_method: Callable[..., Any]

        if isinstance(route_type, APIRoute):
            add_method = router.add_api_route
        elif isinstance(route_type, APIWebSocketRoute):
            add_method = router.add_api_websocket_route
        else:
            raise TypeError(f"Unsupported route type: {type(route_type).__name__}")

        # Read attributes from the original route, not the RouteContext proxy. The proxy
        # (FastAPI >= 0.137.2) only merges path/tags/deps; other fields such as
        # response_model, status_code, and operation_id would be silently lost.
        source_route = getattr(route, "original_route", route)
        valid_params = inspect.signature(add_method).parameters.keys()
        filtered_kwargs = {k: getattr(source_route, k) for k in valid_params if hasattr(source_route, k)}
        filtered_kwargs.setdefault("endpoint", source_route.endpoint)
        # Override path/tags/deps with the merged values from RouteContext when present.
        for merged_attr in ("path", "tags", "dependencies"):
            if hasattr(route, merged_attr) and merged_attr in valid_params:
                filtered_kwargs[merged_attr] = getattr(route, merged_attr)

        # Deprecation flag
        deprecated_in_version = self._extract_version_attribute(route.endpoint, "_deprecate_in_version", route.path)
        if deprecated_in_version is not None:
            if isinstance(version, tuple) and isinstance(deprecated_in_version, tuple):
                if version >= deprecated_in_version:
                    filtered_kwargs["deprecated"] = True
            elif isinstance(version, str) and isinstance(deprecated_in_version, str):
                if version >= deprecated_in_version:
                    filtered_kwargs["deprecated"] = True

        # An empty string name causes an internal FastAPI error; drop it to use the default.
        if "name" in filtered_kwargs and not filtered_kwargs["name"]:
            filtered_kwargs.pop("name")

        add_method(**filtered_kwargs)
