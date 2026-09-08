from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionInfo, api_version


def test_versions_endpoint_generation() -> None:
    """The /versions endpoint lists every active version with links to its docs."""
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


def test_versions_endpoint_aggregates_across_versioners_sharing_an_app() -> None:
    """Two RouterVersioner instances sharing one app (e.g. mixing SemVer and CalVer) must
    both contribute to a single /versions endpoint, not shadow one another: only one GET
    /versions route is registered, and it lists every instance's versions."""
    app = FastAPI()

    semver_router = APIRouter()

    @semver_router.get("/items")
    @api_version((1, 0))
    def items() -> dict[str, str]: ...

    calver_router = APIRouter()

    @calver_router.get("/orders")
    @api_version("2025-01-01")
    def orders() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=semver_router, version_format=VersionFormat.SEMVER, include_versions_route=True
    ).versionize()
    RouterVersioner(
        app=app, routers=calver_router, version_format=VersionFormat.CALVER, include_versions_route=True
    ).versionize()

    matching_routes = [r for r in app.routes if getattr(r, "path", None) == "/versions"]
    assert len(matching_routes) == 1

    client = TestClient(app)
    data = client.get("/versions").json()
    versions = {v["version"] for v in data["versions"]}
    assert versions == {"1.0", "2025-01-01"}


def test_versionize_does_not_write_to_app_state() -> None:
    """Cross-instance bookkeeping (prefix collisions, /versions aggregation) must not leak
    into app.state, a general-purpose namespace any other code holding a reference to the
    app can read or overwrite; it stays private to this package instead."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def items() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=router, version_format=VersionFormat.SEMVER, include_versions_route=True
    ).versionize()

    assert vars(app.state) == {"_state": {}}


def test_versions_route_path_mounts_endpoint_at_a_custom_path() -> None:
    """versions_route_path moves the discovery endpoint off the default /versions; the old
    path stops existing and the custom one serves the same payload."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        include_versions_route=True,
        versions_route_path="/api-versions",
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api-versions" in paths
    assert "/versions" not in paths

    client = TestClient(app)
    assert client.get("/versions").status_code == 404
    data = client.get("/api-versions").json()
    assert [v["version"] for v in data["versions"]] == ["1.0"]


def test_versions_route_path_is_ignored_when_route_is_disabled() -> None:
    """versions_route_path only names where the endpoint goes; it doesn't switch it on.
    With include_versions_route=False, no discovery endpoint is mounted at all."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        include_versions_route=False,
        versions_route_path="/api-versions",
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api-versions" not in paths
    assert "/versions" not in paths


def test_versions_route_path_first_non_none_value_wins_across_versioners() -> None:
    """The aggregated /versions endpoint is mounted once, by the first instance that asks for
    it. That instance fixes the path: a different versions_route_path passed by a later
    instance has no effect, though its versions are still aggregated in."""
    app = FastAPI()

    semver_router = APIRouter()

    @semver_router.get("/items")
    @api_version((1, 0))
    def items() -> dict[str, str]: ...

    calver_router = APIRouter()

    @calver_router.get("/orders")
    @api_version("2025-01-01")
    def orders() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=semver_router,
        version_format=VersionFormat.SEMVER,
        include_versions_route=True,
        versions_route_path="/api-versions",
    ).versionize()
    RouterVersioner(
        app=app,
        routers=calver_router,
        version_format=VersionFormat.CALVER,
        include_versions_route=True,
        versions_route_path="/other-versions",
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api-versions" in paths
    assert "/other-versions" not in paths

    client = TestClient(app)
    data = client.get("/api-versions").json()
    assert {v["version"] for v in data["versions"]} == {"1.0", "2025-01-01"}


def test_versions_route_path_none_keeps_the_default_even_behind_a_custom_first() -> None:
    """Symmetric to the above: when the first instance leaves versions_route_path as None it
    fixes the endpoint at /versions, and a later instance's custom path is still ignored."""
    app = FastAPI()

    semver_router = APIRouter()

    @semver_router.get("/items")
    @api_version((1, 0))
    def items() -> dict[str, str]: ...

    calver_router = APIRouter()

    @calver_router.get("/orders")
    @api_version("2025-01-01")
    def orders() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=semver_router, version_format=VersionFormat.SEMVER, include_versions_route=True
    ).versionize()
    RouterVersioner(
        app=app,
        routers=calver_router,
        version_format=VersionFormat.CALVER,
        include_versions_route=True,
        versions_route_path="/other-versions",
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/versions" in paths
    assert "/other-versions" not in paths


def test_versions_endpoint_omits_doc_links_when_app_openapi_url_is_none() -> None:
    """FastAPI(openapi_url=None) disables Swagger/ReDoc mounting for every version (see
    DocsMounter.mount, which requires app.openapi_url is not None). /versions must not
    advertise swagger_url/redoc_url in that case either, or they'd point at 404s."""
    app = FastAPI(openapi_url=None)
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=router, version_format=VersionFormat.SEMVER, include_versions_route=True
    ).versionize()

    client = TestClient(app)
    version_model = client.get("/versions").json()["versions"][0]
    assert "openapi_url" not in version_model
    assert "swagger_url" not in version_model
    assert "redoc_url" not in version_model


def test_versions_endpoint_includes_the_migration_guide_url_when_set() -> None:
    """VersionInfo.guide is surfaced on /versions as guide_url, verbatim (no root_path), for
    the versions that have one."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item_v1() -> dict[str, str]: ...

    @router.get("/item")
    @api_version((2, 0))
    def item_v2() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        include_versions_route=True,
        version_info={(2, 0): VersionInfo(guide="https://example.com/upgrade/v2")},
    ).versionize()

    by_version = {v["version"]: v for v in TestClient(app).get("/versions").json()["versions"]}
    assert by_version["2.0"]["guide_url"] == "https://example.com/upgrade/v2"
    assert "guide_url" not in by_version["1.0"]
