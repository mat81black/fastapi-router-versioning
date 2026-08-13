from collections.abc import Callable
from typing import Any

import pytest

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version


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
    """A route type RouterVersioner doesn't know how to mount (neither APIRoute nor
    APIWebSocketRoute) raises TypeError."""
    app = FastAPI()
    router = APIRouter()

    class UnsupportedRoute:
        pass

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)

    with pytest.raises(TypeError, match="Unsupported route type: UnsupportedRoute"):
        versioner._add_route_to_router(
            route=UnsupportedRoute(),  # type: ignore
            router=router,
            version=(1, 0),
        )


def test_custom_route_class_is_preserved_on_versioned_routes() -> None:
    """A router built with APIRouter(route_class=CustomRoute) — FastAPI's documented pattern
    for request/response interception via APIRoute.get_route_handler(), e.g. for auth checks
    run before the endpoint — must keep using that class once versioned, not silently fall
    back to plain APIRoute and drop whatever the custom class does.
    """

    class RequireApiKeyRoute(APIRoute):
        def get_route_handler(self) -> Callable[[Request], Any]:
            original_handler = super().get_route_handler()

            async def custom_handler(request: Request) -> Response:
                if request.headers.get("x-api-key") != "secret-internal-key":
                    raise HTTPException(status_code=403, detail="Missing or invalid API key")
                return await original_handler(request)

            return custom_handler

    app = FastAPI()
    router = APIRouter(route_class=RequireApiKeyRoute)

    @router.get("/admin/users")
    @api_version((1, 0))
    def list_admin_users() -> dict[str, list[str]]:
        return {"users": ["alice", "bob"]}

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    assert client.get("/v1_0/admin/users").status_code == 403
    assert client.get("/v1_0/admin/users", headers={"x-api-key": "wrong"}).status_code == 403
    assert client.get("/v1_0/admin/users", headers={"x-api-key": "secret-internal-key"}).status_code == 200


def test_include_router_schema_visibility_override_is_preserved_on_versioned_routes() -> None:
    """include_router(..., include_in_schema=False) hides every route of the included router
    from the OpenAPI schema without affecting routing. That override must still hold once the
    parent router is versioned, not silently revert to the route's own declared value."""
    internal_router = APIRouter()

    @internal_router.get("/debug/internal-state")
    @api_version((1, 0))
    def debug_state() -> dict[str, str]:
        return {"secret": "internal debug info"}

    parent_router = APIRouter()
    parent_router.include_router(internal_router, include_in_schema=False)

    app = FastAPI()
    RouterVersioner(app=app, routers=parent_router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    schema = client.get("/v1_0/openapi.json").json()
    assert "/v1_0/debug/internal-state" not in schema["paths"]
    assert client.get("/v1_0/debug/internal-state").status_code == 200


def test_include_router_deprecated_and_responses_overrides_are_preserved_on_versioned_routes() -> None:
    """FastAPI's own "Bigger Applications" tutorial passes deprecated and responses to
    include_router() to apply them to every route of the included router (e.g.
    responses={418: ...}). Those merged values must survive versioning too."""
    internal_router = APIRouter()

    @internal_router.get("/admin")
    @api_version((1, 0))
    def admin() -> dict[str, bool]:
        return {"ok": True}

    parent_router = APIRouter()
    parent_router.include_router(internal_router, deprecated=True, responses={418: {"description": "I'm a teapot"}})

    app = FastAPI()
    RouterVersioner(app=app, routers=parent_router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    assert client.get("/v1_0/admin").json() == {"ok": True}
    operation = client.get("/v1_0/openapi.json").json()["paths"]["/v1_0/admin"]["get"]
    assert operation["deprecated"] is True
    assert "418" in operation["responses"]


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


def test_versionize_on_router_with_no_routes_returns_empty_list() -> None:
    """A router with no @api_version-decorated routes at all (not even one version boundary)
    must versionize() to an empty list without raising, and must not mount anything for
    latest_prefix either — there is no "latest version" to alias."""
    app = FastAPI()
    router = APIRouter()

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/latest")
    versions = versioner.versionize()

    assert versions == []

    client = TestClient(app)
    assert client.get("/latest").status_code == 404
    assert not any(getattr(r, "path", "").startswith("/latest") for r in app.routes)


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


def test_version_gte_mismatched_types_returns_false() -> None:
    """_version_gte returns False for values that aren't both tuples or both strings.

    Defensive branch: normally unreachable via the public API, since _validate_version_type
    enforces a single, consistent VersionT type (tuple for SEMVER, str for CALVER) per
    RouterVersioner instance.
    """
    assert RouterVersioner._version_gte((1, 0), "2025-01-01") is False
    assert RouterVersioner._version_gte("2025-01-01", (1, 0)) is False


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
