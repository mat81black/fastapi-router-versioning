import pytest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


def test_calver_lifecycle() -> None:
    """Route lifecycle (introduction, persistence, deprecation, removal) with CalVer strings."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/persistent")
    @api_version("2025-01-01")
    def persistent() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/newcomer")
    @api_version("2025-06-01")
    def newcomer() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/lifecycle")
    @api_version("2025-01-01", deprecate_in="2025-06-01", remove_in="2025-12-01")
    def lifecycle() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/future")
    @api_version("2025-12-01")
    def future() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.CALVER)
    versioner.versionize()

    client = TestClient(app)

    # January
    assert client.get("/2025-01-01/persistent").status_code == 200
    assert client.get("/2025-01-01/newcomer").status_code == 404
    assert client.get("/2025-01-01/lifecycle").status_code == 200

    # June
    assert client.get("/2025-06-01/persistent").status_code == 200
    assert client.get("/2025-06-01/newcomer").status_code == 200
    assert client.get("/2025-06-01/lifecycle").status_code == 200

    # December
    assert client.get("/2025-12-01/persistent").status_code == 200
    assert client.get("/2025-12-01/lifecycle").status_code == 404
    assert client.get("/2025-12-01/future").status_code == 200


def test_calver_remove_in_without_start_version() -> None:
    """remove_in is honoured even when no route starts in that version (CalVer).

    Previously the version loop only iterated versions where at least one route
    started, so a version referenced only by remove_in was never processed and
    the route was never removed.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/mortal")
    @api_version("2025-01-01", remove_in="2025-12-01")
    def mortal() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/eternal")
    @api_version("2025-01-01")
    def eternal() -> dict[str, str]:
        return {"msg": "ok"}

    @router.get("/newcomer")
    @api_version("2025-06-01")
    def newcomer() -> dict[str, str]:
        return {"msg": "ok"}

    # No route starts at "2025-12-01"; the version exists solely because of remove_in.
    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.CALVER)
    versions = versioner.versionize()

    assert "2025-12-01" in versions

    client = TestClient(app)

    # January: mortal + eternal
    assert client.get("/2025-01-01/mortal").status_code == 200
    assert client.get("/2025-01-01/eternal").status_code == 200
    assert client.get("/2025-01-01/newcomer").status_code == 404

    # June: mortal still present, newcomer added
    assert client.get("/2025-06-01/mortal").status_code == 200
    assert client.get("/2025-06-01/eternal").status_code == 200
    assert client.get("/2025-06-01/newcomer").status_code == 200

    # December: mortal removed
    assert client.get("/2025-12-01/mortal").status_code == 404
    assert client.get("/2025-12-01/eternal").status_code == 200
    assert client.get("/2025-12-01/newcomer").status_code == 200


def test_calver_type_validation_raises_error() -> None:
    """A tuple version on a CALVER-configured versioner raises ValueError."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/invalid")
    @api_version((1, 0))
    def invalid_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.CALVER)

    with pytest.raises(ValueError, match="RouterVersioner expects CALVER"):
        versioner.versionize()
