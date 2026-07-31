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


def test_websocket_nested_router_prefix_is_preserved() -> None:
    """WebSocket inside a sub-router with a prefix must carry the full merged path when versionized."""
    app = FastAPI()
    ws_router = APIRouter()

    @ws_router.websocket("/ws")
    @api_version((1, 0))
    async def ws_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    parent_router = APIRouter(prefix="/chat")
    parent_router.include_router(ws_router)

    RouterVersioner(app=app, routers=parent_router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    with client.websocket_connect("/v1_0/chat/ws") as ws:
        assert ws.receive_text() == "ok"


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


def test_versioned_app_mounted_as_real_sub_application() -> None:
    """A RouterVersioner-managed app works correctly when actually mounted via app.mount(),
    not just simulated with a root_path passed to TestClient. Covers the ASGI root_path
    FastAPI injects for real sub-applications: versioned docs/openapi and runtime behavior
    must all resolve under the mount prefix."""
    main_app = FastAPI()
    sub_app = FastAPI()
    router = APIRouter()

    @router.post("/items")
    @api_version((1, 0))
    def create_item(count: int) -> dict[str, str]: ...

    RouterVersioner(app=sub_app, routers=router, version_format=VersionFormat.SEMVER).versionize()

    main_app.mount("/sub", sub_app)

    client = TestClient(main_app)

    # Sub-app's own root schema (accessed through the mount) resolves the mount's root_path.
    sub_root_schema = client.get("/sub/openapi.json").json()
    assert "/v1_0/items" in sub_root_schema["paths"]
    assert sub_root_schema["servers"][0]["url"] == "/sub"

    # Versioned schema is consistent too.
    versioned_schema = client.get("/sub/v1_0/openapi.json").json()
    assert versioned_schema["servers"][0]["url"] == "/sub"

    # Runtime resolves correctly through the mount.
    assert client.post("/sub/v1_0/items?count=bad", json={}).status_code == 422
    assert client.get("/sub/v1_0/docs").status_code == 200


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


def test_openapi_hook_is_applied_to_schema() -> None:
    """openapi_hook receives the generated schema and the current version; its return value is served."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    @router.get("/test")
    @api_version((2, 0))
    def test_route_v2() -> dict[str, str]: ...

    def my_hook(schema: dict[str, Any], version: tuple[int, int]) -> dict[str, Any]:
        schema["info"]["x-custom"] = f"v{version[0]}.{version[1]}"
        return schema

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        openapi_hook=my_hook,
    )
    versioner.versionize()

    client = TestClient(app)

    response_v1 = client.get("/v1_0/openapi.json")
    assert response_v1.status_code == 200
    assert response_v1.json()["info"]["x-custom"] == "v1.0"

    response_v2 = client.get("/v2_0/openapi.json")
    assert response_v2.status_code == 200
    assert response_v2.json()["info"]["x-custom"] == "v2.0"


def test_openapi_hook_none_does_not_affect_schema() -> None:
    """When openapi_hook is None (default), the schema is returned unmodified."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    assert "x-custom" not in response.json().get("info", {})


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


def test_remove_in_does_not_evict_a_newer_route_at_the_same_path() -> None:
    """remove_in on a superseded route must not evict the route that replaced it.

    item_v1 is introduced in 1.0 and marked remove_in=3.0. item_v2 replaces it at the same
    (path, method) starting in 2.0. By the time 3.0 processes item_v1's removal, item_v1 is
    no longer the active occupant of that (path, method) key, so the removal must be a no-op:
    item_v2 stays active in 3.0.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0), remove_in=(3, 0))
    def item_v1() -> dict[str, str]:
        return {"v": "1"}

    @router.get("/item")
    @api_version((2, 0))
    def item_v2() -> dict[str, str]:
        return {"v": "2"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versions = versioner.versionize()
    assert versions == [(1, 0), (2, 0), (3, 0)]

    client = TestClient(app)
    assert client.get("/v1_0/item").json() == {"v": "1"}
    assert client.get("/v2_0/item").json() == {"v": "2"}
    # Without the fix, item_v1's remove_in=(3, 0) evicts item_v2 too, since both share the
    # same (path, method) key: this used to 404 instead of resolving to item_v2.
    assert client.get("/v3_0/item").json() == {"v": "2"}


def test_deprecate_in_alone_creates_the_deprecation_version() -> None:
    """deprecate_in must produce a version boundary even when it's the only lifecycle change
    on the route: otherwise the version where the deprecation becomes observable never exists.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0), deprecate_in=(2, 0))
    def get_item() -> dict[str, str]:
        return {"v": "1"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versions = versioner.versionize()
    # Without the fix, only (1, 0) is generated: (2, 0) is absent from both introduced and
    # removed, so it never enters the version set.
    assert versions == [(1, 0), (2, 0)]

    client = TestClient(app)
    # The route is still active (and reachable) in both versions.
    assert client.get("/v1_0/item").status_code == 200
    assert client.get("/v2_0/item").status_code == 200

    schema_v1 = client.get("/v1_0/openapi.json").json()
    schema_v2 = client.get("/v2_0/openapi.json").json()
    assert schema_v1["paths"]["/v1_0/item"]["get"].get("deprecated") is None
    assert schema_v2["paths"]["/v2_0/item"]["get"]["deprecated"] is True


def test_multi_method_route_is_mounted_once() -> None:
    """A route declared with multiple HTTP methods (methods=["GET", "POST"]) occupies one
    (path, method) key per method in the internal bookkeeping, all pointing to the same route
    object: it must still be mounted on the versioned router exactly once, not once per method.
    """
    import functools

    from unittest.mock import patch

    app = FastAPI()
    router = APIRouter()

    @router.api_route("/item", methods=["GET", "POST"])
    @api_version((1, 0))
    def item() -> dict[str, bool]:
        return {"ok": True}

    original_add_api_route = APIRouter.add_api_route
    calls_for_item: list[str] = []

    # inspect.signature(add_method) inside _add_route_to_router relies on the real
    # add_api_route signature to build its kwargs; functools.wraps keeps that intact.
    @functools.wraps(original_add_api_route)
    def spy(self: APIRouter, *args: Any, **kwargs: Any) -> Any:
        path = kwargs.get("path", args[0] if args else None)
        if path == "/item":
            calls_for_item.append(path)
        return original_add_api_route(self, *args, **kwargs)

    with patch.object(APIRouter, "add_api_route", spy):
        RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()

    # Without the fix, add_api_route is called once per method sharing the (path, method) keys
    # generated for the same route, i.e. twice for methods=["GET", "POST"].
    assert len(calls_for_item) == 1

    client = TestClient(app)
    assert client.get("/v1_0/item").status_code == 200
    assert client.post("/v1_0/item").status_code == 200


def test_dedicated_route_takes_over_one_method_of_a_multi_method_route() -> None:
    """A dedicated single-method route can replace just one method of an earlier multi-method
    route, without the multi-method route's stale copy of that method resurfacing.

    item_multi handles GET+POST from 1.0. item_post_v2 takes over POST alone from 2.0. At 2.0,
    item_multi must be re-mounted with GET only: mounting it with its original full method set
    (GET+POST) would re-register POST for it too, colliding with item_post_v2.
    """
    app = FastAPI()
    router = APIRouter()

    @router.api_route("/item", methods=["GET", "POST"])
    @api_version((1, 0))
    def item_multi() -> dict[str, str]:
        return {"handler": "multi"}

    @router.post("/item")
    @api_version((2, 0))
    def item_post_v2() -> dict[str, str]:
        return {"handler": "post_v2"}

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    assert client.get("/v1_0/item").json() == {"handler": "multi"}
    assert client.post("/v1_0/item").json() == {"handler": "multi"}

    # GET is untouched, still served by item_multi. POST is now exclusively item_post_v2's,
    # not a stale duplicate coming from item_multi's original method set.
    assert client.get("/v2_0/item").json() == {"handler": "multi"}
    assert client.post("/v2_0/item").json() == {"handler": "post_v2"}

    schema = client.get("/v2_0/openapi.json").json()
    assert sorted(schema["paths"]["/v2_0/item"].keys()) == ["get", "post"]


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
    """include_version_openapi_route=False: /openapi.json returns 404. /docs and /redoc must
    also be disabled, since both fetch their schema from that same, now-missing URL; leaving
    them mounted would only produce a docs page stuck on a fetch error.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        include_version_docs=True,
        include_version_openapi_route=False,
        include_versions_route=True,
    )
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/openapi.json").status_code == 404
    assert client.get("/v1_0/docs").status_code == 404
    assert client.get("/v1_0/redoc").status_code == 404

    version_model = client.get("/versions").json()["versions"][0]
    assert "openapi_url" not in version_model
    assert "swagger_url" not in version_model
    assert "redoc_url" not in version_model


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


def test_routers_as_list() -> None:
    """routers accepts a list of APIRouter, not just a single one (multi-router support)."""
    app = FastAPI()
    router1 = APIRouter()
    router2 = APIRouter()

    @router1.get("/a")
    @api_version((1, 0))
    def route_a() -> dict[str, str]:
        return {"msg": "a"}

    @router2.get("/b")
    @api_version((1, 0))
    def route_b() -> dict[str, str]:
        return {"msg": "b"}

    RouterVersioner(app=app, routers=[router1, router2], version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    assert client.get("/v1_0/a").status_code == 200
    assert client.get("/v1_0/b").status_code == 200


def test_openapi_callbacks_are_propagated_to_versioned_routes() -> None:
    """OpenAPI callbacks defined on a route are propagated to every versioned copy of that route."""
    app = FastAPI()
    callback_router = APIRouter()

    @callback_router.post("{$url}")
    def on_item_created(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.post("/items", callbacks=callback_router.routes)
    @api_version((1, 0))
    def create_item() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    post_op = schema["paths"]["/v1_0/items"]["post"]
    assert "callbacks" in post_op
    assert len(post_op["callbacks"]) > 0


def test_webhook_routers_are_versioned_per_version() -> None:
    """webhook_routers: each version's OpenAPI schema shows only the webhooks active in that version."""
    app = FastAPI()

    webhook_router = APIRouter()

    @webhook_router.post("/order-created")
    @api_version((1, 0))
    def webhook_v1(body: dict[str, str]) -> None: ...

    @webhook_router.post("/order-created")
    @api_version((2, 0))
    def webhook_v2(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    @router.get("/orders")
    @api_version((2, 0))
    def get_orders() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        webhook_routers=webhook_router,
        version_format=VersionFormat.SEMVER,
    )
    versioner.versionize()

    client = TestClient(app)

    schema_v1 = client.get("/v1_0/openapi.json").json()
    schema_v2 = client.get("/v2_0/openapi.json").json()

    # v1: webhook_v1 active (introduced at (1,0))
    assert "/order-created" in schema_v1.get("webhooks", {})
    # v2: webhook_v2 supersedes webhook_v1 (same path+method key → only one entry)
    assert "/order-created" in schema_v2.get("webhooks", {})


def test_webhook_routers_remove_in_removes_webhook_from_version() -> None:
    """Webhooks with remove_in are absent from that version onwards."""
    app = FastAPI()

    webhook_router = APIRouter()

    @webhook_router.post("/ping")
    @api_version((1, 0), remove_in=(2, 0))
    def webhook_ping(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    @router.get("/items")
    @api_version((2, 0))
    def get_items_v2() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        webhook_routers=webhook_router,
        version_format=VersionFormat.SEMVER,
    )
    versioner.versionize()

    client = TestClient(app)

    schema_v1 = client.get("/v1_0/openapi.json").json()
    schema_v2 = client.get("/v2_0/openapi.json").json()

    assert "/ping" in schema_v1.get("webhooks", {})
    assert "/ping" not in schema_v2.get("webhooks", {})


def test_webhook_routers_none_falls_back_to_app_webhooks() -> None:
    """When webhook_routers is not provided, every version inherits app.webhooks."""
    app = FastAPI()

    @app.webhooks.post("/global-event")
    def global_webhook(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    schema_v1 = client.get("/v1_0/openapi.json").json()
    assert "/global-event" in schema_v1.get("webhooks", {})


def test_webhook_routers_as_list() -> None:
    """webhook_routers accepts a list of APIRouter, not just a single one."""
    app = FastAPI()
    router = APIRouter()
    webhook_router1 = APIRouter()
    webhook_router2 = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    @webhook_router1.post("/hook-a")
    @api_version((1, 0))
    def hook_a(body: dict[str, str]) -> None: ...

    @webhook_router2.post("/hook-b")
    @api_version((1, 0))
    def hook_b(body: dict[str, str]) -> None: ...

    RouterVersioner(
        app=app,
        routers=router,
        webhook_routers=[webhook_router1, webhook_router2],
        version_format=VersionFormat.SEMVER,
    ).versionize()

    client = TestClient(app)
    schema = client.get("/v1_0/openapi.json").json()
    assert "/hook-a" in schema.get("webhooks", {})
    assert "/hook-b" in schema.get("webhooks", {})


def test_webhook_routers_no_webhook_before_first_version() -> None:
    """When all webhook versions are higher than the current route version, returns no webhooks."""
    app = FastAPI()
    webhook_router = APIRouter()

    @webhook_router.post("/late")
    @api_version((2, 0))
    def webhook_late(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    @router.get("/orders")
    @api_version((2, 0))
    def get_orders() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=router, webhook_routers=webhook_router, version_format=VersionFormat.SEMVER
    ).versionize()

    client = TestClient(app)
    # v1: webhook introduced at (2,0) → no webhooks yet
    schema_v1 = client.get("/v1_0/openapi.json").json()
    assert not schema_v1.get("webhooks")
    # v2: webhook present
    schema_v2 = client.get("/v2_0/openapi.json").json()
    assert "/late" in schema_v2.get("webhooks", {})


def test_webhook_routers_calver() -> None:
    """webhook_routers work with CalVer versioning (covers the str branch in _resolve_webhooks_for_version)."""
    app = FastAPI()
    webhook_router = APIRouter()

    @webhook_router.post("/event")
    @api_version("2025-01")
    def webhook_v1(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version("2025-01")
    def get_items() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=router, webhook_routers=webhook_router, version_format=VersionFormat.CALVER
    ).versionize()

    client = TestClient(app)
    schema = client.get("/2025-01/openapi.json").json()
    assert "/event" in schema.get("webhooks", {})


def test_openapi_schema_is_cached() -> None:
    """The schema is generated only once; subsequent requests use the cache."""
    from unittest.mock import patch

    import fastapi.openapi.utils as openapi_utils

    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0))
    def get_data() -> dict[str, str]: ...

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()
    client = TestClient(app)

    with patch.object(openapi_utils, "get_openapi", wraps=openapi_utils.get_openapi) as mock_fn:
        client.get("/v1_0/openapi.json")
        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 1


def test_openapi_cache_invalidated_on_route_change() -> None:
    """The cache is invalidated when _get_routes_version() changes after a new route is added."""
    from unittest.mock import patch

    import fastapi.openapi.utils as openapi_utils

    import fastapi_router_versioning.versioner as versioner_mod

    if versioner_mod._route_contexts_fn is None:
        pytest.skip("_get_routes_version not available (FastAPI < 0.137.2)")  # pragma: no cover

    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0))
    def get_data() -> dict[str, str]: ...

    captured_routers: dict[Any, APIRouter] = {}

    def capture_callback(versioned_router: APIRouter, version: VersionT, prefix: str) -> None:
        captured_routers[version] = versioned_router

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, callback=capture_callback)
    versioner.versionize()
    client = TestClient(app)

    with patch.object(openapi_utils, "get_openapi", wraps=openapi_utils.get_openapi) as mock_fn:
        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 1

        captured_routers[(1, 0)].add_api_route("/dynamic", lambda: {}, methods=["GET"])

        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 2


def test_version_gte_mismatched_types_returns_false() -> None:
    """_version_gte returns False for values that aren't both tuples or both strings.

    Defensive branch: normally unreachable via the public API, since _validate_version_type
    enforces a single, consistent VersionT type (tuple for SEMVER, str for CALVER) per
    RouterVersioner instance.
    """
    assert RouterVersioner._version_gte((1, 0), "2025-01-01") is False
    assert RouterVersioner._version_gte("2025-01-01", (1, 0)) is False


def test_duplicate_version_prefix_across_versioners_raises() -> None:
    """Two RouterVersioners producing the same version prefix on the same app must fail fast
    instead of silently shadowing each other's docs/openapi routes."""
    app = FastAPI()
    router1 = APIRouter()
    router2 = APIRouter()

    @router1.get("/a")
    @api_version((1, 0))
    def route_a() -> dict[str, str]: ...

    @router2.get("/b")
    @api_version((1, 0))
    def route_b() -> dict[str, str]: ...

    RouterVersioner(app=app, routers=router1, version_format=VersionFormat.SEMVER).versionize()

    with pytest.raises(RuntimeError, match="already used by another RouterVersioner"):
        RouterVersioner(app=app, routers=router2, version_format=VersionFormat.SEMVER).versionize()


def test_degenerate_prefix_format_self_collision_raises() -> None:
    """A prefix_format without {major}/{minor}/{version} placeholders makes every version
    resolve to the same prefix. This is a self-collision on a single instance, not a clash
    with another RouterVersioner, so the error message must say so explicitly."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items_v1() -> dict[str, str]: ...

    @router.get("/items")
    @api_version((2, 0))
    def get_items_v2() -> dict[str, str]: ...

    with pytest.raises(RuntimeError, match="already claimed by this same RouterVersioner instance"):
        RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, prefix_format="/api").versionize()


def test_latest_prefix_collides_with_own_version_prefix_raises() -> None:
    """latest_prefix accidentally set to the same value as an actual version's own prefix is
    a self-collision on a single instance, not a clash with another RouterVersioner."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    with pytest.raises(RuntimeError, match="already claimed by this same RouterVersioner instance"):
        RouterVersioner(
            app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/v1_0"
        ).versionize()


def test_calling_versionize_twice_on_same_instance_raises() -> None:
    """Calling .versionize() a second time on the same instance must raise a clear,
    self-explanatory error instead of the misleading '...used by another RouterVersioner'
    message that _claim_prefix would otherwise produce (it's the same instance, not another)."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    with pytest.raises(RuntimeError, match="versionize\\(\\) was already called on this RouterVersioner instance"):
        versioner.versionize()


def test_duplicate_latest_prefix_across_versioners_raises() -> None:
    """Two RouterVersioners sharing the same latest_prefix on the same app must fail fast."""
    app = FastAPI()
    router1 = APIRouter()
    router2 = APIRouter()

    @router1.get("/a")
    @api_version((1, 0))
    def route_a() -> dict[str, str]: ...

    @router2.get("/b")
    @api_version("2025-01-01")
    def route_b() -> dict[str, str]: ...

    RouterVersioner(app=app, routers=router1, version_format=VersionFormat.SEMVER, latest_prefix="/latest").versionize()

    with pytest.raises(RuntimeError, match="already used by another RouterVersioner"):
        RouterVersioner(
            app=app, routers=router2, version_format=VersionFormat.CALVER, latest_prefix="/latest"
        ).versionize()


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
        result = list(versioner_module.RouterVersioner._iter_routes_flat(router.routes))
        assert result == list(router.routes)
    finally:
        versioner_module._route_contexts_fn = original_fn
