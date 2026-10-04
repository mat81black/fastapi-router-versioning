from collections.abc import Callable
from typing import Annotated, Any

from annotated_doc import Doc
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
    """Versions a FastAPI app in place: one router per active version, each mounted under its
    own prefix with its own OpenAPI schema and documentation pages.

    The configuration is validated here, in ``__init__``; nothing is mounted until ``versionize()``
    is called, and it may only be called once.
    """

    def __init__(
        self,
        app: Annotated[FastAPI, Doc("The main FastAPI application instance.")],
        routers: Annotated[
            list[APIRouter] | APIRouter,
            Doc("A single `APIRouter` or a list of them, containing the routes to version."),
        ],
        version_format: Annotated[
            VersionFormat,
            Doc(
                'The versioning strategy, which fixes the type every version must have. For `CALVER`, version strings must sort lexicographically in the intended order (ISO dates like `"2025-01-01"`, zero-padded numbers like `"v01"`, `"v02"`); `"v1"`, `"v10"`, `"v2"` do not, and routes would appear in the wrong versions.'
            ),
        ] = VersionFormat.SEMVER,
        prefix_format: Annotated[
            str | None,
            Doc(
                "Template for each version's URL prefix; supports `{major}`, `{minor}` and `{version}`. Defaults to `/v{major}_{minor}` under SemVer and `/{version}` under CalVer."
            ),
        ] = None,
        semantic_version_format: Annotated[
            str | None,
            Doc(
                "Template for the version label in the Swagger/ReDoc titles; same placeholders. Defaults to `{major}.{minor}` under SemVer and `{version}` under CalVer."
            ),
        ] = None,
        default_version: Annotated[
            VersionT | None,
            Doc(
                'Version given to routes that are not decorated with `@api_version`. Defaults to `(1, 0)` under SemVer and `"1"` under CalVer.'
            ),
        ] = None,
        latest_prefix: Annotated[
            str | None,
            Doc('If set (for example `"/latest"`), also mounts the newest active version under this prefix.'),
        ] = None,
        include_version_docs: Annotated[bool, Doc("Create a Swagger UI and a ReDoc page for each version.")] = True,
        include_version_openapi_route: Annotated[
            bool, Doc("Create a separate `openapi.json` route for each version.")
        ] = True,
        include_versions_route: Annotated[
            bool, Doc("Add a `GET` endpoint returning information on every active version.")
        ] = False,
        versions_route_path: Annotated[
            str,
            Doc(
                "Path of that endpoint; must start with `/`. Has no effect unless `include_versions_route` is `True`. When several `RouterVersioner` instances share one app, the endpoint is mounted once by the first of them to enable it, and that instance fixes its path; a different path on a later instance is ignored."
            ),
        ] = "/versions",
        include_versions_dashboard: Annotated[
            bool,
            Doc(
                "Add an HTML page listing every active version with links to its docs (and to its `VersionInfo.guide`, when `version_info` gives one). The built-in page shows `app.title` and `app.version`. Same data as the versions endpoint, but independent of it, and kept out of the OpenAPI schema."
            ),
        ] = False,
        versions_dashboard_path: Annotated[
            str,
            Doc(
                "Path of that page; must start with `/`. Has no effect unless `include_versions_dashboard` is `True`. Same first-instance-wins rule as `versions_route_path`."
            ),
        ] = "/dashboard",
        versions_dashboard_hook: Annotated[
            Callable[[list[dict[str, Any]], str], str] | None,
            Doc(
                "Renderer replacing the built-in dashboard page. Receives the aggregated version models (the same dicts the versions endpoint returns) and the request `root_path`, and must return the full HTML. App metadata is not passed: a hook that wants it reads `app.title` / `app.version` from its own app reference."
            ),
        ] = None,
        deprecation_headers: Annotated[
            bool,
            Doc(
                'If `True`, every response of a route in its deprecation window carries these headers, built once at `versionize()` time: `Deprecation` and `Link: rel="deprecation"` (RFC 9745), `Sunset` (RFC 8594), `Link: rel="successor-version"` (RFC 5829). Dates and guide URLs come from `version_info`; without it only the successor-version link is emitted, since it needs no configuration.'
            ),
        ] = False,
        version_info: Annotated[
            dict[VersionT, VersionInfo] | None,
            Doc(
                "Mapping of version to its `VersionInfo` (release date and/or upgrade-guide URL); keys must match `version_format`. The fields feed the deprecation headers only when `deprecation_headers` is `True`, and with it on `versionize()` raises if a route's `remove_in` date precedes its `deprecate_in` date. `VersionInfo.guide` is also listed per version on the versions endpoint and the dashboard regardless. A version absent from the map, or a field left `None`, yields nothing for that part, with no warning."
            ),
        ] = None,
        sort_routes: Annotated[bool, Doc("Sort all routes alphabetically by path.")] = False,
        callback: Annotated[
            Callable[[APIRouter, VersionT, str], None] | None,
            Doc(
                "Called with `(router, version, prefix)` for every versioned router, including the `latest_prefix` alias, right before it is included in the app."
            ),
        ] = None,
        webhook_routers: Annotated[
            list[APIRouter] | APIRouter | None,
            Doc(
                "A single `APIRouter` or a list of them, holding webhook definitions annotated with `@api_version`. Each version's OpenAPI schema then shows only the webhooks active in it, using the same introduce/remove lifecycle as routes. When `None`, every version inherits `app.webhooks` unchanged."
            ),
        ] = None,
        openapi_hook: Annotated[
            Callable[[dict[str, Any], VersionT], dict[str, Any]] | None,
            Doc(
                "Applied to the OpenAPI schema generated for each version. Receives the schema dict and the version, and must return the (possibly modified) schema. Use it to add extensions, logos or version-specific metadata that the per-version schema generation would otherwise bypass."
            ),
        ] = None,
        swagger_js_url: Annotated[
            str | None, Doc("URL of the Swagger UI JS bundle. Defaults to FastAPI's CDN URL.")
        ] = None,
        swagger_css_url: Annotated[str | None, Doc("URL of the Swagger UI CSS. Defaults to FastAPI's CDN URL.")] = None,
        swagger_favicon_url: Annotated[
            str | None, Doc("URL of the Swagger UI favicon. Defaults to FastAPI's favicon.")
        ] = None,
        redoc_js_url: Annotated[str | None, Doc("URL of the ReDoc JS bundle. Defaults to FastAPI's CDN URL.")] = None,
        redoc_favicon_url: Annotated[
            str | None, Doc("URL of the ReDoc favicon. Defaults to FastAPI's favicon.")
        ] = None,
        redoc_with_google_fonts: Annotated[bool, Doc("If `False`, ReDoc does not load Google Fonts.")] = True,
    ) -> None:
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
    def _validate_route_path(path: str, param_name: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            error_msg = f"{param_name} must start with '/', got {path!r}."
            raise ValueError(error_msg)
        return path

    def versionize(self) -> list[VersionT]:
        """
        Reads the configured routers, groups their routes by version, and mounts one
        versioned router per active version on the app. Returns the versions that were
        actually mounted.

        May only be called once per instance: a second call raises ``RuntimeError``. If it
        raises, the app failed to load: don't catch the exception and retry, since some
        versions may already be mounted and this package makes no attempt to undo that.

        Raises ``ValueError`` if a route's ``@api_version`` does not match the configured
        ``version_format``, or if ``version_info`` dates a route's ``remove_in`` before its
        ``deprecate_in`` while ``deprecation_headers`` is on. Raises ``RuntimeError`` if a
        prefix is already taken, by this instance or by another RouterVersioner on the same
        app. Raises ``TypeError`` if a router holds a route that is neither an HTTP nor a
        WebSocket route.
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
