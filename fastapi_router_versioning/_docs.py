"""Each version's own openapi.json, Swagger UI and ReDoc pages, plus the schema cache behind
them and the URLs at which they answer.
"""

from collections.abc import Callable
from enum import Enum
from typing import Any, TypeAlias

import fastapi.openapi.utils

from fastapi import APIRouter, FastAPI, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse
from fastapi.routing import APIRoute

from ._scheme import VersionScheme
from ._versions import VersionT

_OpenAPICacheKey: TypeAlias = tuple[VersionT, str]


class DocsMounter:
    """Mounts the documentation routes of one version onto that version's router, and knows
    the URLs they end up on. One instance per RouterVersioner: the OpenAPI schema cache is
    shared across every version it serves, keyed by (version, prefix).
    """

    def __init__(
        self,
        app: FastAPI,
        scheme: VersionScheme,
        *,
        include_version_docs: bool,
        include_version_openapi_route: bool,
        docs_url: str | None,
        redoc_url: str | None,
        openapi_hook: Callable[[dict[str, Any], VersionT], dict[str, Any]] | None,
        swagger_js_url: str | None,
        swagger_css_url: str | None,
        swagger_favicon_url: str | None,
        redoc_js_url: str | None,
        redoc_favicon_url: str | None,
        redoc_with_google_fonts: bool,
    ) -> None:
        self._app = app
        self._scheme = scheme
        self._include_version_docs = include_version_docs
        self._include_version_openapi_route = include_version_openapi_route
        self._docs_url = docs_url
        self._redoc_url = redoc_url
        self._openapi_hook = openapi_hook
        self._swagger_js_url = swagger_js_url
        self._swagger_css_url = swagger_css_url
        self._swagger_favicon_url = swagger_favicon_url
        self._redoc_js_url = redoc_js_url
        self._redoc_favicon_url = redoc_favicon_url
        self._redoc_with_google_fonts = redoc_with_google_fonts
        self._schemas_cache: dict[_OpenAPICacheKey, dict[str, Any]] = {}
        self._routes_versions: dict[_OpenAPICacheKey, int | None] = {}

    def mount(self, router: APIRouter, version: VersionT, version_prefix: str, webhooks: list[Any]) -> None:
        doc_version_str = self._scheme.doc_version(version)
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

    def version_urls(self, version_prefix: str, root_path: str) -> dict[str, str]:
        """The documentation URLs this version actually answers on, under the given root_path.
        The conditions mirror mount() exactly: a URL is listed only when the route behind it
        was mounted. openapi_url is read per call because it is the app's live attribute.
        """
        urls: dict[str, str] = {}
        openapi_url = self._app.openapi_url

        if self._include_version_openapi_route and openapi_url is not None:
            urls["openapi_url"] = f"{root_path}{version_prefix}{openapi_url}"
        if (
            self._include_version_docs
            and self._include_version_openapi_route
            and self._docs_url is not None
            and openapi_url is not None
        ):
            urls["swagger_url"] = f"{root_path}{version_prefix}{self._docs_url}"
        if (
            self._include_version_docs
            and self._include_version_openapi_route
            and self._redoc_url is not None
            and openapi_url is not None
        ):
            urls["redoc_url"] = f"{root_path}{version_prefix}{self._redoc_url}"

        return urls

    def _collect_versioned_tags(self, router: APIRouter) -> list[dict[str, Any]]:
        if self._app.openapi_tags is None:
            return []
        tags: set[str] = set()
        for route in router.routes:
            if isinstance(route, APIRoute) and isinstance(route.tags, list):
                tags.update(tag.value if isinstance(tag, Enum) else tag for tag in route.tags)
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

            cached = self._schemas_cache.get(cache_key)
            if cached is None or self._routes_versions.get(cache_key) != current_routes_version:
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
                self._schemas_cache[cache_key] = schema
                self._routes_versions[cache_key] = current_routes_version
            else:
                schema = self._schemas_cache[cache_key]

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
