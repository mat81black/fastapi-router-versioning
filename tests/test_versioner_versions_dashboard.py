from typing import Any

import pytest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionInfo, api_version


def _semver_router() -> APIRouter:
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item() -> dict[str, str]: ...

    return router


def test_dashboard_mounts_at_default_path() -> None:
    """include_versions_dashboard mounts an HTML page at /dashboard listing every active
    version with links to its docs."""
    app = FastAPI()

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
    ).versionize()

    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")

    body = response.text
    assert "1.0" in body
    assert "/v1_0/docs" in body
    assert "/v1_0/redoc" in body
    assert "/v1_0/openapi.json" in body


def test_dashboard_shows_the_app_title_and_version() -> None:
    """The built-in page's heading is app.title, with app.version next to it; both are
    HTML-escaped since app.title is free text."""
    app = FastAPI(title="Payments & Billing", version="3.2.1")

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
    ).versionize()

    body = TestClient(app).get("/dashboard").text
    assert "Payments &amp; Billing" in body
    assert "Payments & Billing" not in body
    assert "3.2.1" in body


def test_dashboard_is_disabled_by_default() -> None:
    app = FastAPI()

    RouterVersioner(app=app, routers=_semver_router(), version_format=VersionFormat.SEMVER).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/dashboard" not in paths


def test_dashboard_is_kept_out_of_the_openapi_schema() -> None:
    """The page returns HTML, not a documented model, so it must not show up in /openapi.json
    (same choice FastAPI makes for its own /docs and /redoc)."""
    app = FastAPI()

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
    ).versionize()

    schema_paths = TestClient(app).get("/openapi.json").json()["paths"]
    assert "/dashboard" not in schema_paths


def test_dashboard_custom_path() -> None:
    app = FastAPI()

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
        versions_dashboard_path="/ui/versions",
    ).versionize()

    client = TestClient(app)
    assert client.get("/dashboard").status_code == 404
    assert client.get("/ui/versions").status_code == 200


def test_dashboard_works_without_the_json_versions_route() -> None:
    """The dashboard aggregates the same data as GET /versions but does not depend on it:
    enabling only the dashboard still registers this instance's versions."""
    app = FastAPI()

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_route=False,
        include_versions_dashboard=True,
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/versions" not in paths

    body = TestClient(app).get("/dashboard").text
    assert "1.0" in body
    assert "/v1_0/docs" in body


def test_dashboard_aggregates_across_versioners_sharing_an_app() -> None:
    """Two RouterVersioner instances on one app contribute to a single dashboard, mounted
    once, listing every instance's versions."""
    app = FastAPI()

    calver_router = APIRouter()

    @calver_router.get("/order")
    @api_version("2025-01-01")
    def order() -> dict[str, str]: ...

    RouterVersioner(
        app=app, routers=_semver_router(), version_format=VersionFormat.SEMVER, include_versions_dashboard=True
    ).versionize()
    RouterVersioner(
        app=app, routers=calver_router, version_format=VersionFormat.CALVER, include_versions_dashboard=True
    ).versionize()

    dashboards = [r for r in app.routes if getattr(r, "path", None) == "/dashboard"]
    assert len(dashboards) == 1

    body = TestClient(app).get("/dashboard").text
    assert "1.0" in body
    assert "2025-01-01" in body


def test_dashboard_first_path_wins_across_versioners() -> None:
    app = FastAPI()

    calver_router = APIRouter()

    @calver_router.get("/order")
    @api_version("2025-01-01")
    def order() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
        versions_dashboard_path="/first",
    ).versionize()
    RouterVersioner(
        app=app,
        routers=calver_router,
        version_format=VersionFormat.CALVER,
        include_versions_dashboard=True,
        versions_dashboard_path="/second",
    ).versionize()

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/first" in paths
    assert "/second" not in paths

    body = TestClient(app).get("/first").text
    assert "1.0" in body
    assert "2025-01-01" in body


def test_dashboard_hook_replaces_the_renderer() -> None:
    """versions_dashboard_hook takes over rendering entirely and receives the aggregated
    version models plus the request root_path."""
    app = FastAPI()
    seen: dict[str, Any] = {}

    def hook(versions: list[dict[str, Any]], root_path: str) -> str:
        seen["versions"] = versions
        seen["root_path"] = root_path
        return "<p>custom dashboard</p>"

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
        versions_dashboard_hook=hook,
    ).versionize()

    response = TestClient(app).get("/dashboard")
    assert response.text == "<p>custom dashboard</p>"
    assert seen["root_path"] == ""
    assert [m["version"] for m in seen["versions"]] == ["1.0"]
    assert seen["versions"][0]["swagger_url"] == "/v1_0/docs"


def test_dashboard_renders_without_doc_links_when_app_openapi_url_is_none() -> None:
    """FastAPI(openapi_url=None) disables every per-version docs route, so the page has a
    row for the version but no links to follow."""
    app = FastAPI(openapi_url=None)

    RouterVersioner(
        app=app,
        routers=_semver_router(),
        version_format=VersionFormat.SEMVER,
        include_versions_dashboard=True,
    ).versionize()

    body = TestClient(app).get("/dashboard").text
    assert "1.0" in body
    assert "no docs" in body
    assert "/v1_0/docs" not in body


def test_dashboard_path_without_leading_slash_raises() -> None:
    app = FastAPI()

    with pytest.raises(ValueError, match="versions_dashboard_path must start with '/'"):
        RouterVersioner(
            app=app,
            routers=_semver_router(),
            version_format=VersionFormat.SEMVER,
            include_versions_dashboard=True,
            versions_dashboard_path="dashboard",
        )


def test_dashboard_lists_the_migration_guide_per_version() -> None:
    """VersionInfo.guide is shown on the dashboard for the versions that have one, and needs
    no deprecation_headers to appear."""
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
        include_versions_dashboard=True,
        version_info={(2, 0): VersionInfo(guide="https://example.com/upgrade/v2")},
    ).versionize()

    body = TestClient(app).get("/dashboard").text
    assert '<a href="https://example.com/upgrade/v2">Guide</a>' in body
    assert body.count(">Guide</a>") == 1  # only v2 has a guide; v1's row has none
