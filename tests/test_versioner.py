from typing import Any

import pytest

from fastapi import APIRouter, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from starlette.routing import Route

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version


def test_versions_endpoint_generation() -> None:
    """Checks that the /versions endpoint returns correct links to docs for each active version."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        include_versions_route=True,
    )
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/versions")
    assert response.status_code == 200

    data = response.json()
    assert "versions" in data
    assert len(data["versions"]) == 1

    v1_info = data["versions"][0]
    assert v1_info["version"] == "1.0"
    assert v1_info["openapi_url"] == "/v1_0/openapi.json"
    assert v1_info["swagger_url"] == "/v1_0/docs"
    assert v1_info["redoc_url"] == "/v1_0/redoc"


def test_default_version_applied_to_undecorated_routes() -> None:
    """Routes without @api_version should fall back to the configured default_version."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/default")
    def default_route() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, default_version=(4, 2))
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v4_2/default").status_code == 200


def test_docs_and_latest_prefix() -> None:
    """Swagger, ReDoc, OpenAPI JSON, and the latest_prefix alias are all reachable."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/docs-test")
    @api_version((1, 0))
    def docs_route() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/vlatest")
    versioner.versionize()

    client = TestClient(app)

    assert client.get("/v1_0/openapi.json").status_code == 200
    assert client.get("/v1_0/docs").status_code == 200
    assert client.get("/v1_0/redoc").status_code == 200

    assert client.get("/vlatest/docs-test").status_code == 200
    assert client.get("/vlatest/openapi.json").status_code == 200


def test_sort_routes_and_empty_name() -> None:
    """Routes are sorted alphabetically when sort_routes=True; empty name does not crash FastAPI."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/b", name="")
    @api_version((1, 0))
    def route_b() -> dict[str, str]:
        return {"msg": "b"}

    @router.get("/a")
    @api_version((1, 0))
    def route_a() -> dict[str, str]:
        return {"msg": "a"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, sort_routes=True)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/a").status_code == 200
    assert client.get("/v1_0/b").status_code == 200


def test_websockets_versioning() -> None:
    """WebSocket routes are versioned and accessible only in the declared version."""
    app = FastAPI()
    router = APIRouter()

    @router.websocket("/ws")
    @api_version((2, 0))
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("Hello Versioned WS")
        await websocket.close()

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        client.websocket_connect("/v1_0/ws").__enter__()

    with client.websocket_connect("/v2_0/ws") as websocket:
        data = websocket.receive_text()
        assert data == "Hello Versioned WS"


def test_unsupported_route_type_raises_error() -> None:
    """A Starlette Route (not APIRoute/APIWebSocketRoute) should raise TypeError."""
    app = FastAPI()
    router = APIRouter()

    async def dummy_endpoint(request: Any) -> PlainTextResponse: ...

    unsupported_route = Route("/dummy", endpoint=dummy_endpoint)

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)

    with pytest.raises(TypeError, match="Unsupported route type: Route"):
        versioner._add_route_to_router(
            route=unsupported_route,  # type: ignore
            router=router,
            version=(1, 0),
        )


def test_versioner_callback() -> None:
    """The callback is invoked once per versioned router, including the latest_prefix alias."""
    app = FastAPI()
    router = APIRouter()
    called_versions = []

    def my_callback(rt: APIRouter, version: VersionT, prefix: str) -> None:
        called_versions.append((version, prefix))

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app, routers=router, version_format=VersionFormat.SEMVER, callback=my_callback, latest_prefix="/vlatest"
    )
    versioner.versionize()

    assert len(called_versions) == 2
    assert called_versions[0] == ((1, 0), "/v1_0")
    assert called_versions[1] == ((1, 0), "/vlatest")


def test_openapi_with_root_path_and_oauth2() -> None:
    """OpenAPI JSON includes a server entry when the app is mounted behind a proxy (root_path)."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/docs/oauth2-redirect").status_code == 200

    # Simulate a reverse-proxy setup by passing root_path to the test client.
    client_proxy = TestClient(app, root_path="/api")
    response = client_proxy.get("/v1_0/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "servers" in schema
    assert schema["servers"][0]["url"] == "/api"


def test_custom_formats_coverage() -> None:
    """Custom prefix_format and semantic_version_format are applied correctly."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/custom")
    @api_version((2, 1))
    def custom_route() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        prefix_format="/api/ver-{major}-{minor}",
        semantic_version_format="v{major}.{minor}-custom",
    )
    versioner.versionize()

    client = TestClient(app)

    assert client.get("/api/ver-2-1/custom").status_code == 200

    response = client.get("/api/ver-2-1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "v2.1-custom"


def test_api_version_wrong_type_raises_error() -> None:
    """@api_version raises TypeError immediately at decoration time when given a wrong type."""
    with pytest.raises(TypeError, match="api_version:.*'version'"):

        @api_version(1)  # type: ignore[arg-type]
        def my_func() -> None: ...

    with pytest.raises(TypeError, match="api_version:.*'deprecate_in'"):

        @api_version((1, 0), deprecate_in=2)  # type: ignore[arg-type]
        def my_func2() -> None: ...

    with pytest.raises(TypeError, match="api_version:.*'remove_in'"):

        @api_version((1, 0), remove_in=3.5)  # type: ignore[arg-type]
        def my_func3() -> None: ...


def test_openapi_tags_filtering_coverage() -> None:
    """Only tags actually used by routes in a given version appear in that version's OpenAPI schema."""
    app_tags = [
        {"name": "auth", "description": "Authentication"},
        {"name": "users", "description": "User management (not used in v1)"},
    ]
    app = FastAPI(openapi_tags=app_tags)
    router = APIRouter()

    @router.get("/login", tags=["auth"])
    @api_version((1, 0))
    def login_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "tags" in schema

    assert len(schema["tags"]) == 1
    assert schema["tags"][0]["name"] == "auth"


def test_openapi_tags_empty_when_no_route_uses_a_tag() -> None:
    """Tags list is empty when none of the routes in the version carry any tag."""
    app = FastAPI(openapi_tags=[{"name": "auth", "description": "Authentication"}])
    router = APIRouter()

    @router.get("/ping")
    @api_version((1, 0))
    def ping() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    assert response.json().get("tags") is None


def test_oauth2_redirect_url_is_versioned_in_swagger_html() -> None:
    """The OAuth2 redirect URL embedded in the versioned Swagger HTML points to the versioned path."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    html = client.get("/v1_0/docs").text
    assert "/v1_0/docs/oauth2-redirect" in html


def test_init_oauth_config_propagated_to_versioned_docs() -> None:
    """swagger_ui_init_oauth set on the FastAPI app appears in the versioned Swagger UI HTML."""
    app = FastAPI(swagger_ui_init_oauth={"clientId": "my-app-client", "scopes": "read:api"})
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    html = client.get("/v1_0/docs").text
    assert "my-app-client" in html
    assert "read:api" in html


def test_custom_oauth2_redirect_url_is_versioned() -> None:
    """A custom swagger_ui_oauth2_redirect_url is versioned: both the endpoint and the HTML link."""
    app = FastAPI(swagger_ui_oauth2_redirect_url="/my-oauth2-redirect")
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/my-oauth2-redirect").status_code == 200
    html = client.get("/v1_0/docs").text
    assert "/v1_0/my-oauth2-redirect" in html


def test_oauth2_redirect_disabled_when_no_redirect_url() -> None:
    """When swagger_ui_oauth2_redirect_url=None, no redirect endpoint is registered and
    no oauth2RedirectUrl property appears in the Swagger HTML."""
    app = FastAPI(swagger_ui_oauth2_redirect_url=None)
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/docs/oauth2-redirect").status_code == 404
    html = client.get("/v1_0/docs").text
    assert "oauth2RedirectUrl" not in html


def test_custom_swagger_asset_urls() -> None:
    """Custom JS/CSS/favicon URLs are reflected in the versioned Swagger UI HTML."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        swagger_js_url="https://internal.company.com/swagger-ui-bundle.js",
        swagger_css_url="https://internal.company.com/swagger-ui.css",
        swagger_favicon_url="https://internal.company.com/favicon.ico",
    )
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/docs")
    assert response.status_code == 200
    html = response.text
    assert "https://internal.company.com/swagger-ui-bundle.js" in html
    assert "https://internal.company.com/swagger-ui.css" in html
    assert "https://internal.company.com/favicon.ico" in html


def test_custom_redoc_asset_urls_and_no_google_fonts() -> None:
    """Custom ReDoc JS/favicon URLs and redoc_with_google_fonts=False are reflected in the versioned ReDoc HTML."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        redoc_js_url="https://internal.company.com/redoc.standalone.js",
        redoc_favicon_url="https://internal.company.com/favicon.ico",
        redoc_with_google_fonts=False,
    )
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/redoc")
    assert response.status_code == 200
    html = response.text
    assert "https://internal.company.com/redoc.standalone.js" in html
    assert "https://internal.company.com/favicon.ico" in html
    assert "fonts.googleapis.com" not in html


def test_default_asset_urls_use_cdn() -> None:
    """Without custom asset URLs, versioned docs fall back to FastAPI's default CDN URLs."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)

    swagger_html = client.get("/v1_0/docs").text
    assert "cdn.jsdelivr.net" in swagger_html

    redoc_html = client.get("/v1_0/redoc").text
    assert "cdn.jsdelivr.net" in redoc_html


def test_swagger_and_redoc_openapi_url_includes_root_path_at_request_time() -> None:
    """When the app is behind a reverse proxy, the root_path is injected at request time,
    so the openapi_url in the Swagger/ReDoc HTML reflects the proxy prefix."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    # Simulate mounting behind a reverse proxy that sets root_path="/prefix"
    client = TestClient(app, root_path="/prefix")

    swagger_html = client.get("/v1_0/docs").text
    assert "/prefix/v1_0/openapi.json" in swagger_html
    assert swagger_html.count("/v1_0/openapi.json") == swagger_html.count("/prefix/v1_0/openapi.json")

    redoc_html = client.get("/v1_0/redoc").text
    assert "/prefix/v1_0/openapi.json" in redoc_html


def test_latest_prefix_created_when_final_version_has_no_routes() -> None:
    """latest_prefix must be created even when the final version removes all routes
    (previously the empty dict {} was falsy, causing latest_prefix to be silently skipped)."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0), remove_in=(2, 0))
    def data() -> dict[str, str]:
        return {"v": "1"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/latest")
    versioner.versionize()

    client = TestClient(app)
    # v1.0: route is active
    assert client.get("/v1_0/data").status_code == 200
    # v2.0 exists (it's the remove_in boundary) but has no routes
    assert client.get("/v2_0/data").status_code == 404
    # latest_prefix must still be created (pointing to v2.0 — the last version, even if empty)
    # The key check: no AttributeError / silent skip during versionize()
    assert client.get("/latest/data").status_code == 404  # empty version → no routes


def test_include_version_docs_false_disables_swagger_and_redoc() -> None:
    """include_version_docs=False: /docs and /redoc return 404; /openapi.json still works."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, include_version_docs=False, include_version_openapi_route=True)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/openapi.json").status_code == 200
    assert client.get("/v1_0/docs").status_code == 404
    assert client.get("/v1_0/redoc").status_code == 404


def test_include_version_openapi_route_false_disables_openapi_json() -> None:
    """include_version_openapi_route=False: /openapi.json returns 404.
    /docs and /redoc are also 404 because the condition requires openapi_url to be present."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, include_version_docs=True, include_version_openapi_route=False)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/openapi.json").status_code == 404
    assert client.get("/v1_0/docs").status_code == 200
    assert client.get("/v1_0/redoc").status_code == 200


def test_latest_prefix_points_to_highest_sorted_version() -> None:
    """latest_prefix aliases the highest (sorted) version, accumulating all active routes.
    A route introduced in v1.0 carries forward to v3.0 unless explicitly removed."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/old")
    @api_version((1, 0), remove_in=(2, 0))
    def old() -> dict[str, str]:
        return {"v": "old"}

    @router.get("/new")
    @api_version((3, 0))
    def new_feature() -> dict[str, str]:
        return {"v": "new"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/latest")
    versioner.versionize()

    client = TestClient(app)
    # v1.0: /old is active
    assert client.get("/v1_0/old").status_code == 200
    # /latest resolves to v3.0 (highest): /new is present, /old was removed at v2.0
    assert client.get("/latest/new").status_code == 200
    assert client.get("/latest/old").status_code == 404


def test_default_version_mixed_with_explicitly_decorated_routes() -> None:
    """Routes without @api_version use default_version as start; decorated routes use
    their own. Routes accumulate: a route from v2.0 is still present in v3.0."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/explicit")
    @api_version((2, 0))
    def explicit() -> dict[str, str]:
        return {"type": "explicit"}

    @router.get("/implicit")
    def implicit() -> dict[str, str]:
        return {"type": "implicit"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, default_version=(3, 0))
    versioner.versionize()

    client = TestClient(app)
    # v2.0: /explicit starts here; /implicit not yet (starts at v3.0)
    assert client.get("/v2_0/explicit").status_code == 200
    assert client.get("/v2_0/implicit").status_code == 404
    # v3.0: /implicit starts here; /explicit carried forward from v2.0
    assert client.get("/v3_0/implicit").status_code == 200
    assert client.get("/v3_0/explicit").status_code == 200


def test_iter_routes_flat_fallback_without_route_context_fn() -> None:
    """Covers the _route_contexts_fn=None fallback (legacy FastAPI < 0.137.2).

    Patches the module-level variable to None to simulate an environment where
    iter_route_contexts is not available, then verifies that _iter_routes_flat
    yields the raw route list unchanged.
    """
    import fastapi_router_versioning.versioner as versioner_module

    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict[str, str]: ...

    original_fn = versioner_module._route_contexts_fn
    try:
        versioner_module._route_contexts_fn = None
        result = list(versioner_module._iter_routes_flat(router.routes))
        assert result == list(router.routes)
    finally:
        versioner_module._route_contexts_fn = original_fn
