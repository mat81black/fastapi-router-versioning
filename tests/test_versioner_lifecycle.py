from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


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
