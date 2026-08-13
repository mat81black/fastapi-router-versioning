from typing import Any

import pytest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version


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


def test_versionize_callback_failure_is_fatal_and_propagates() -> None:
    """A callback raising partway through versionize() is a fatal, unrecoverable error: it
    must propagate as-is, not be swallowed or wrapped."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item_v1() -> dict[str, int]: ...

    @router.get("/item")
    @api_version((2, 0))
    def item_v2() -> dict[str, int]: ...

    processed_versions: list[VersionT] = []

    def failing_callback(_router: APIRouter, version: VersionT, _prefix: str) -> None:
        processed_versions.append(version)
        if version == (2, 0):
            raise ValueError("simulated failure while processing v2")

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, callback=failing_callback)

    with pytest.raises(ValueError, match="simulated failure while processing v2"):
        versioner.versionize()

    assert processed_versions == [(1, 0), (2, 0)]


def test_versionize_rejects_retry_after_a_failed_attempt() -> None:
    """Once versionize() has failed, this same instance must never be usable again: the
    FastAPI app it was building may already be partially mounted, so silently allowing a
    second attempt could paper over a broken, half-versioned app instead of surfacing it."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item() -> dict[str, str]: ...

    def failing_callback(_router: APIRouter, _version: VersionT, _prefix: str) -> None:
        raise ValueError("boom")

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, callback=failing_callback)

    with pytest.raises(ValueError, match="boom"):
        versioner.versionize()

    with pytest.raises(RuntimeError, match="versionize\\(\\) was already called on this RouterVersioner instance"):
        versioner.versionize()


def test_versionize_commit_phase_failure_propagates_and_blocks_retry() -> None:
    """A failure during the commit phase (after every version was already prepared
    successfully, so some versions may already be mounted) is fatal, exactly like a failure
    during the prepare phase: it propagates as-is, and this instance is never usable again.
    """
    from unittest.mock import patch

    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item_v1() -> dict[str, int]:
        return {"v": 1}

    @router.get("/item")
    @api_version((2, 0))
    def item_v2() -> dict[str, int]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)

    original_include_router = FastAPI.include_router
    calls = {"count": 0}

    def failing_include_router(self: FastAPI, *args: Any, **kwargs: Any) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise ValueError("simulated failure while mounting the second version")
        original_include_router(self, *args, **kwargs)

    with patch.object(FastAPI, "include_router", failing_include_router):
        with pytest.raises(ValueError, match="simulated failure while mounting the second version"):
            versioner.versionize()

    # v1 was mounted before v2's include_router call failed: the app is left partially
    # mounted on purpose, since nothing here attempts to undo it.
    client = TestClient(app)
    assert client.get("/v1_0/item").status_code == 200
    assert client.get("/v2_0/item").status_code == 404

    with pytest.raises(RuntimeError, match="versionize\\(\\) was already called on this RouterVersioner instance"):
        versioner.versionize()
