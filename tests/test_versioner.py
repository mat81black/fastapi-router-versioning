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
