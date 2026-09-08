"""RouterVersioner: the package's entry point.

Normalizes and validates the configuration, then drives one versionize() run: group the
routes by version, build a router per version, mount them on the app, and add the shared
discovery routes. The work itself lives in the private modules alongside this one.
"""

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, FastAPI

from ._builder import VersionRouterBuilder
from ._deprecation import DeprecationPolicy
from ._docs import DocsMounter
from ._lifecycle import collect_routes_by_version, collect_webhooks_by_version, resolve_webhooks_for_version
from ._registry import (
    add_version_provider,
    check_prefix_available,
    claim_prefix,
    mount_versions_dashboard,
    mount_versions_route,
)
from ._scheme import VersionScheme, validate_version_info
from ._versions import VersionFormat, VersionInfo, VersionT, version_field


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
        versions_route_path: str | None = None,
        include_versions_dashboard: bool = False,
        versions_dashboard_path: str | None = None,
        versions_dashboard_hook: Callable[[list[dict[str, Any]], str], str] | None = None,
        deprecation_headers: bool = False,
        version_info: dict[VersionT, VersionInfo] | None = None,
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
        :param versions_route_path: Path for that endpoint; defaults to '/versions' when None. Must start with '/'.
            Has no effect unless include_versions_route is True. When several RouterVersioner instances share one app,
            the endpoint is mounted once by the first of them to enable it, and that instance fixes its path (None or
            not); a different versions_route_path on a later instance is ignored.
        :param include_versions_dashboard: If True, adds an HTML page listing every active version with links to its
            docs (and to its VersionInfo.guide, when version_info gives one). The built-in page shows app.title and
            app.version. Same aggregated data as the /versions JSON route, but independent of it; kept out of the
            OpenAPI schema.
        :param versions_dashboard_path: Path for that page; defaults to '/dashboard' when None. Must start with '/'.
            Has no effect unless include_versions_dashboard is True. Same first-instance-wins rule as versions_route_path.
        :param versions_dashboard_hook: Optional renderer replacing the built-in dashboard page. Receives the aggregated
            version models (the same dicts the /versions JSON returns) and the request root_path; must return the full HTML.
            App metadata is not passed: a hook that wants it reads app.title / app.version off its own app reference.
        :param deprecation_headers: If True, every response of a route in its deprecation window carries standards-based
            headers, built once at versionize() time: RFC 9745 'Deprecation' and 'Link: rel="deprecation"', RFC 8594
            'Sunset', RFC 5829 'Link: rel="successor-version"'. Off by default; the dates and guide URLs come from
            version_info. With no version_info only the successor-version link is emitted (it needs no config).
        :param version_info: Optional mapping of version -> VersionInfo carrying that version's calendar date and/or
            upgrade-guide URL. VersionInfo.release_date and VersionInfo.guide feed the headers above (release_date at
            deprecate_in -> 'Deprecation', at remove_in -> 'Sunset'; guide at deprecate_in -> 'Link: rel="deprecation"')
            only when deprecation_headers is True, and with it on versionize() raises if a route's remove_in date precedes
            its deprecate_in date. VersionInfo.guide is also listed per version on the '/versions' JSON endpoint and the
            versions dashboard, regardless of deprecation_headers. A version absent from the map, or a VersionInfo field
            left None, simply yields nothing for that part (no warning). Keys must match the version_format in use.
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
        self._webhook_routers: list[APIRouter] | None = (
            [webhook_routers] if isinstance(webhook_routers, APIRouter) else webhook_routers
        )

        self._versions_route_path = self._validate_route_path(versions_route_path, "versions_route_path")
        self._versions_dashboard_path = self._validate_route_path(versions_dashboard_path, "versions_dashboard_path")
        self._scheme = VersionScheme.build(version_format, prefix_format, semantic_version_format, default_version)
        self._version_info = validate_version_info(version_info, self._scheme)

        self._latest_prefix = latest_prefix
        self._include_versions_route = include_versions_route
        self._include_versions_dashboard = include_versions_dashboard
        self._versions_dashboard_hook = versions_dashboard_hook
        self._callback = callback

        self._docs = DocsMounter(
            app,
            self._scheme,
            include_version_docs=include_version_docs,
            include_version_openapi_route=include_version_openapi_route,
            docs_url=getattr(app, "docs_url", "/docs"),
            redoc_url=getattr(app, "redoc_url", "/redoc"),
            openapi_hook=openapi_hook,
            swagger_js_url=swagger_js_url,
            swagger_css_url=swagger_css_url,
            swagger_favicon_url=swagger_favicon_url,
            redoc_js_url=redoc_js_url,
            redoc_favicon_url=redoc_favicon_url,
            redoc_with_google_fonts=redoc_with_google_fonts,
        )
        self._deprecation = DeprecationPolicy(
            enabled=deprecation_headers, version_info=self._version_info, scheme=self._scheme
        )
        self._builder = VersionRouterBuilder(app, self._scheme, self._docs, self._deprecation, sort_routes=sort_routes)

        self._versionized = False

    @staticmethod
    def _validate_route_path(path: str | None, param_name: str) -> str | None:
        if path is not None and not path.startswith("/"):
            error_msg = f"{param_name} must start with '/', got {path!r}."
            raise ValueError(error_msg)
        return path

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

        routes_by_version = collect_routes_by_version(self._routers, self._scheme)
        self._deprecation.validate_lifecycle_dates(self._routers)
        versions = list(routes_by_version.keys())
        webhooks_by_version = collect_webhooks_by_version(self._webhook_routers, self._scheme)
        # webhook_routers not provided: every version falls back to the global app.webhooks
        app_webhooks = None if self._webhook_routers is not None else list(self._app.webhooks.routes)

        prepared: list[tuple[str, APIRouter]] = []
        staged_prefixes: set[str] = set()
        latest_version: VersionT | None = None
        latest_routes: dict[tuple[str, str], Any] = {}
        latest_webhooks: list[Any] = []

        for version, routes_by_key in routes_by_version.items():
            version_prefix = self._scheme.prefix(version)
            check_prefix_available(self._app, version_prefix, staged_prefixes)
            staged_prefixes.add(version_prefix)

            active_webhooks = resolve_webhooks_for_version(version, webhooks_by_version, app_webhooks)
            version_router = self._builder.build(
                version=version,
                version_prefix=version_prefix,
                routes_by_key=routes_by_key,
                webhooks=active_webhooks,
                routes_by_version=routes_by_version,
            )
            if self._callback:
                self._callback(version_router, version, version_prefix)

            prepared.append((version_prefix, version_router))
            latest_version = version
            latest_routes = routes_by_key
            latest_webhooks = active_webhooks

        if self._latest_prefix is not None and latest_version is not None:
            check_prefix_available(self._app, self._latest_prefix, staged_prefixes)
            staged_prefixes.add(self._latest_prefix)

            latest_router = self._builder.build(
                version=latest_version,
                version_prefix=self._latest_prefix,
                routes_by_key=latest_routes,
                webhooks=latest_webhooks,
                routes_by_version=routes_by_version,
            )
            if self._callback:
                self._callback(latest_router, latest_version, self._latest_prefix)
            prepared.append((self._latest_prefix, latest_router))

        for prefix, _router in prepared:
            claim_prefix(self._app, prefix)
        for _prefix, router in prepared:
            self._app.include_router(router=router)
        if self._include_versions_route or self._include_versions_dashboard:
            add_version_provider(self._app, lambda root_path: self._build_version_models(versions, root_path))
        if self._include_versions_route:
            mount_versions_route(self._app, self._versions_route_path)
        if self._include_versions_dashboard:
            mount_versions_dashboard(self._app, self._versions_dashboard_path, self._versions_dashboard_hook)

        return versions

    def _build_version_models(self, versions: list[VersionT], root_path: str) -> list[dict[str, Any]]:
        version_models: list[dict[str, Any]] = []
        for version in versions:
            version_model: dict[str, Any] = {"version": self._scheme.doc_version(version)}
            version_model.update(self._docs.version_urls(self._scheme.prefix(version), root_path))

            # VersionInfo.guide is an external URL (an upgrade guide page), not an app path:
            # emitted verbatim, no root_path prefix, independent of deprecation_headers.
            guide = version_field(self._version_info, version, "guide")
            if guide is not None:
                version_model["guide_url"] = guide

            version_models.append(version_model)

        return version_models
