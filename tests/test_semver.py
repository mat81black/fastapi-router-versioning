import pytest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


def test_semver_lifecycle() -> None:
    """Route lifecycle (introduction, persistence, deprecation, removal) with SemVer tuples."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/persistent")
    @api_version((1, 0))
    def persistent() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/newcomer")
    @api_version((2, 0))
    def newcomer() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/lifecycle")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def lifecycle() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/future")
    @api_version((3, 0))
    def future() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)

    # v1.0
    assert client.get("/v1_0/persistent").status_code == 200
    assert client.get("/v1_0/newcomer").status_code == 404
    assert client.get("/v1_0/lifecycle").status_code == 200
    assert client.get("/v1_0/future").status_code == 404

    # v2.0
    assert client.get("/v2_0/persistent").status_code == 200
    assert client.get("/v2_0/newcomer").status_code == 200
    assert client.get("/v2_0/lifecycle").status_code == 200
    assert client.get("/v2_0/future").status_code == 404

    # v3.0
    assert client.get("/v3_0/persistent").status_code == 200
    assert client.get("/v3_0/newcomer").status_code == 200
    assert client.get("/v3_0/lifecycle").status_code == 404
    assert client.get("/v3_0/future").status_code == 200


def test_semver_remove_in_without_start_version() -> None:
    """remove_in is honoured even when no route starts in that version.

    Previously the version loop only iterated versions where at least one route
    started, so a version referenced only by remove_in was never processed and
    the route was never removed.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/mortal")
    @api_version((1, 0), remove_in=(3, 0))
    def mortal() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/eternal")
    @api_version((1, 0))
    def eternal() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/newcomer")
    @api_version((2, 0))
    def newcomer() -> dict[str, str]:
        return {"msg": "ok"}

    # No route starts at (3, 0); the version exists solely because of remove_in.
    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versions = versioner.versionize()

    assert (3, 0) in versions

    client = TestClient(app)

    # v1.0: mortal + eternal present
    assert client.get("/v1_0/mortal").status_code == 200
    assert client.get("/v1_0/eternal").status_code == 200
    assert client.get("/v1_0/newcomer").status_code == 404

    # v2.0: mortal still present, newcomer added
    assert client.get("/v2_0/mortal").status_code == 200
    assert client.get("/v2_0/eternal").status_code == 200
    assert client.get("/v2_0/newcomer").status_code == 200

    # v3.0: mortal removed, eternal and newcomer present
    assert client.get("/v3_0/mortal").status_code == 404
    assert client.get("/v3_0/eternal").status_code == 200
    assert client.get("/v3_0/newcomer").status_code == 200


def test_semver_type_validation_raises_error() -> None:
    """A string version on a SEMVER-configured versioner raises ValueError."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/invalid")
    @api_version("2025-01-01")
    def invalid_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)

    with pytest.raises(ValueError, match="RouterVersioner expects SEMVER"):
        versioner.versionize()
