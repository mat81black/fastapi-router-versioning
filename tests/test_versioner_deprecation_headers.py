"""Runtime deprecation signalling: RFC 9745 Deprecation, RFC 8594 Sunset, RFC 8288/5829
Link headers derived at versionize() time from the declarative lifecycle plus the
version_info map.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest

from fastapi import APIRouter, FastAPI, Request, Response, WebSocket
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionInfo, api_version

DEPRECATE_EPOCH = int(datetime(2025, 3, 1, tzinfo=timezone.utc).timestamp())
REMOVE_HTTP_DATE = "Thu, 01 Jan 2026 00:00:00 GMT"

FULL_INFO: dict[Any, VersionInfo] = {
    (1, 0): VersionInfo(release_date=date(2024, 1, 15)),
    (2, 0): VersionInfo(release_date=date(2025, 3, 1), guide="https://example.com/migrate/v2"),
    (3, 0): VersionInfo(release_date=date(2026, 1, 1)),
}


def _retiring_route_app(version_info: dict[Any, VersionInfo] | None = FULL_INFO, **kwargs: Any) -> FastAPI:
    """One route, introduced v1, deprecated v2, removed v3. Same handler serves it in v1 and
    v2 (no replacement), so v2 is a real deprecation window.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/report")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def report() -> dict[str, str]:
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info=version_info,
        **kwargs,
    ).versionize()
    return app


def test_no_headers_before_the_deprecation_boundary() -> None:
    client = TestClient(_retiring_route_app())
    resp = client.get("/v1_0/report")
    assert resp.status_code == 200
    assert "deprecation" not in resp.headers
    assert "sunset" not in resp.headers
    assert "link" not in resp.headers


def test_full_header_set_in_the_deprecation_window() -> None:
    client = TestClient(_retiring_route_app())
    resp = client.get("/v2_0/report")

    assert resp.status_code == 200
    assert resp.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"
    assert resp.headers["sunset"] == REMOVE_HTTP_DATE
    # The route is gone in v3, so there is no successor to point at: only the migration link.
    assert resp.headers["link"] == '<https://example.com/migrate/v2>; rel="deprecation"'


def test_deprecated_flag_lands_in_the_per_version_schema_without_touching_the_description() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/doc")
    @api_version((1, 0), deprecate_in=(2, 0))
    def doc() -> dict[str, str]:
        """The original summary line."""
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
    ).versionize()

    client = TestClient(app)
    assert client.get("/v1_0/doc").status_code == 200
    assert client.get("/v2_0/doc").status_code == 200
    op_v1 = client.get("/v1_0/openapi.json").json()["paths"]["/v1_0/doc"]["get"]
    op_v2 = client.get("/v2_0/openapi.json").json()["paths"]["/v2_0/doc"]["get"]
    assert op_v1.get("deprecated") is None
    assert op_v2["deprecated"] is True
    # version_info drives headers only: the route's own description is left as it was.
    assert op_v1["description"] == "The original summary line."
    assert op_v2["description"] == "The original summary line."


def test_headers_gone_again_once_the_route_is_removed() -> None:
    client = TestClient(_retiring_route_app())
    assert client.get("/v3_0/report").status_code == 404


def test_successor_link_points_to_the_next_version_that_keeps_the_route() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/keep")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(4, 0))
    def keep() -> dict[str, str]:
        return {"v": "1"}

    # A filler route so (3, 0) is a real version between the deprecate and remove boundaries.
    @router.get("/filler")
    @api_version((3, 0))
    def filler() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
    ).versionize()

    client = TestClient(app)
    assert client.get("/v3_0/filler").status_code == 200
    # Deprecated at v2, still served at v3 -> successor link to /v3_0/keep.
    resp2 = client.get("/v2_0/keep")
    assert resp2.headers["link"] == '</v3_0/keep>; rel="successor-version"'
    # At v3 the route lives on but v4 removes it: nothing later to point at.
    resp3 = client.get("/v3_0/keep")
    assert "link" not in resp3.headers
    assert resp3.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"


def test_successor_link_is_root_path_aware() -> None:
    """The successor-version path is client-visible, so it must carry root_path (proxy prefix,
    sub-app mount), resolved per request like this package's docs/openapi routes."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/keep")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(4, 0))
    def keep() -> dict[str, str]:
        return {"v": "1"}

    @router.get("/filler")
    @api_version((3, 0))
    def filler() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1), guide="https://x.test/g")},
    ).versionize()

    client = TestClient(app, root_path="/api")
    assert client.get("/v3_0/filler").status_code == 200
    resp = client.get("/v2_0/keep")
    assert resp.headers["link"] == ('</api/v3_0/keep>; rel="successor-version", <https://x.test/g>; rel="deprecation"')
    # The guide link (an absolute URL) is untouched by root_path.


def test_successor_and_guide_links_are_combined() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/both")
    @api_version((1, 0), deprecate_in=(2, 0))
    def both() -> dict[str, str]:
        return {}

    @router.get("/filler")
    @api_version((3, 0))
    def filler() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1), guide="https://x.test/m")},
    ).versionize()

    client = TestClient(app)
    assert client.get("/v3_0/filler").status_code == 200
    resp = client.get("/v2_0/both")
    assert resp.headers["link"] == '</v3_0/both>; rel="successor-version", <https://x.test/m>; rel="deprecation"'


def test_deprecation_present_but_sunset_omitted_when_remove_version_has_no_date() -> None:
    # (3, 0) is absent from version_info -> Sunset has no date to use, dropped (no warning).
    client = TestClient(_retiring_route_app(version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))}))
    resp = client.get("/v2_0/report")
    assert resp.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"
    assert "sunset" not in resp.headers
    assert "link" not in resp.headers


def test_flag_off_by_default_ignores_version_info() -> None:
    """deprecation_headers defaults to False: no wrapper, no headers, even with version_info."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/report")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def report() -> dict[str, str]:
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        version_info=FULL_INFO,  # present, but the flag is off
    ).versionize()

    resp = TestClient(app).get("/v2_0/report")
    assert resp.status_code == 200
    assert "deprecation" not in resp.headers
    assert "sunset" not in resp.headers
    assert "link" not in resp.headers


def test_flag_on_without_version_info_emits_only_the_successor_link() -> None:
    """deprecation_headers=True with no version_info: the successor link needs no config,
    Deprecation/Sunset/guide have no data so they are simply absent.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/keep")
    @api_version((1, 0), deprecate_in=(2, 0))
    def keep() -> dict[str, str]:
        return {"v": "1"}

    @router.get("/filler")
    @api_version((3, 0))
    def filler() -> dict[str, str]:
        return {}

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, deprecation_headers=True).versionize()

    client = TestClient(app)
    assert client.get("/v3_0/filler").status_code == 200
    resp = client.get("/v2_0/keep")
    assert resp.headers["link"] == '</v3_0/keep>; rel="successor-version"'
    assert "deprecation" not in resp.headers
    assert "sunset" not in resp.headers


def test_a_versioninfo_with_only_a_guide_still_emits_the_deprecation_link() -> None:
    client = TestClient(_retiring_route_app(version_info={(2, 0): VersionInfo(guide="https://x.test/only")}))
    resp = client.get("/v2_0/report")
    assert "deprecation" not in resp.headers
    assert "sunset" not in resp.headers
    assert resp.headers["link"] == '<https://x.test/only>; rel="deprecation"'


def test_guide_for_a_different_version_is_not_used() -> None:
    # version_info only describes (3, 0); the route is deprecated at (2, 0) -> no guide link.
    client = TestClient(_retiring_route_app(version_info={(3, 0): VersionInfo(guide="https://example.com/v3")}))
    resp = client.get("/v2_0/report")
    assert "deprecation" not in resp.headers
    assert "link" not in resp.headers


def test_our_link_goes_out_as_its_own_field_beside_the_callers() -> None:
    """RFC 8288: multiple Link fields combine. We add ours as a separate line instead of
    reading/rewriting the caller's, so a caller emitting several Link lines keeps all of them.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/withlinks")
    @api_version((1, 0), deprecate_in=(2, 0))
    def with_links(response: Response) -> dict[str, str]:
        response.headers["Link"] = '<https://x.test/prev>; rel="prev"'
        response.headers.append("Link", '<https://x.test/next>; rel="next"')
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1), guide="https://x.test/m")},
    ).versionize()

    resp = TestClient(app).get("/v2_0/withlinks")
    assert resp.headers.get_list("link") == [
        '<https://x.test/prev>; rel="prev"',
        '<https://x.test/next>; rel="next"',
        '<https://x.test/m>; rel="deprecation"',
    ]
    assert resp.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"


def test_a_caller_set_deprecation_header_is_not_overwritten() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/own")
    @api_version((1, 0), deprecate_in=(2, 0))
    def own(response: Response) -> dict[str, str]:
        response.headers["Deprecation"] = "@1"
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
    ).versionize()

    resp = TestClient(app).get("/v2_0/own")
    assert resp.headers["deprecation"] == "@1"  # setdefault: ours does not clobber theirs


def test_headers_compose_with_a_custom_route_class() -> None:
    seen: list[str] = []

    class TracingRoute(APIRoute):
        def get_route_handler(self) -> Any:
            downstream = super().get_route_handler()

            async def handler(request: Request) -> Response:
                seen.append(request.url.path)
                return await downstream(request)

            return handler

    app = FastAPI()
    router = APIRouter(route_class=TracingRoute)

    @router.get("/traced")
    @api_version((1, 0), deprecate_in=(2, 0))
    def traced() -> dict[str, str]:
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
    ).versionize()

    resp = TestClient(app).get("/v2_0/traced")
    assert resp.json() == {"v": "1"}
    assert resp.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"  # deprecation wrapper ran
    assert seen == ["/v2_0/traced"]  # and the custom class's own handler ran too


def test_custom_route_class_is_subclassed_once_for_many_deprecated_routes() -> None:
    """The deprecation subclass is memoized per base class: a custom route_class's
    __init_subclass__ fires once, not once per deprecated route mounted across versions.
    """
    subclassed: list[str] = []

    class CountingRoute(APIRoute):
        def __init_subclass__(cls, **kwargs: Any) -> None:
            super().__init_subclass__(**kwargs)
            subclassed.append(cls.__name__)

    app = FastAPI()
    router = APIRouter(route_class=CountingRoute)

    @router.get("/a")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(4, 0))
    def a() -> dict[str, str]:
        return {}

    @router.get("/b")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(4, 0))
    def b() -> dict[str, str]:
        return {}

    @router.get("/filler")
    @api_version((3, 0))
    def filler() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1)), (4, 0): VersionInfo()},
    ).versionize()

    # 2 routes x 2 deprecation-window versions (v2, v3) = 4 mounts + include_router copies,
    # yet the CountingRoute subclass is created exactly once.
    assert subclassed == ["_DeprecationHeadersRoute"]
    client = TestClient(app)
    assert client.get("/v3_0/filler").status_code == 200
    assert client.get("/v2_0/a").headers["deprecation"] == f"@{DEPRECATE_EPOCH}"
    assert client.get("/v3_0/b").headers["deprecation"] == f"@{DEPRECATE_EPOCH}"


def test_latest_prefix_alias_also_carries_the_headers() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/still")
    @api_version((1, 0), deprecate_in=(2, 0))
    def still() -> dict[str, str]:
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
        latest_prefix="/latest",
    ).versionize()

    resp = TestClient(app).get("/latest/still")
    assert resp.headers["deprecation"] == f"@{DEPRECATE_EPOCH}"


def test_websocket_route_in_deprecation_window_is_not_wrapped() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.websocket("/ws")
    @api_version((1, 0), deprecate_in=(2, 0))
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text("ok")
        await websocket.close()

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2025, 3, 1))},
    ).versionize()

    client = TestClient(app)
    with client.websocket_connect("/v2_0/ws") as connection:
        assert connection.receive_text() == "ok"


def test_calver_version_info_feeds_the_headers() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/c")
    @api_version("2024-01-01", deprecate_in="2025-01-01", remove_in="2026-01-01")
    def c() -> dict[str, str]:
        return {"v": "1"}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.CALVER,
        deprecation_headers=True,
        version_info={
            "2025-01-01": VersionInfo(release_date=date(2025, 1, 1), guide="https://example.com/calver-guide"),
            "2026-01-01": VersionInfo(release_date=date(2026, 1, 1)),
        },
    ).versionize()

    resp = TestClient(app).get("/2025-01-01/c")
    assert resp.headers["deprecation"] == f"@{int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp())}"
    assert resp.headers["sunset"] == "Thu, 01 Jan 2026 00:00:00 GMT"
    assert resp.headers["link"] == '<https://example.com/calver-guide>; rel="deprecation"'


def test_version_info_date_accepts_datetime_and_reads_naive_as_utc() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/d")
    @api_version((1, 0), deprecate_in=(2, 0))
    def d() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=datetime(2025, 3, 1, 12, 30))},  # naive -> read as UTC
    ).versionize()

    resp = TestClient(app).get("/v2_0/d")
    expected = int(datetime(2025, 3, 1, 12, 30, tzinfo=timezone.utc).timestamp())
    assert resp.headers["deprecation"] == f"@{expected}"


def test_version_info_date_accepts_an_aware_datetime() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/a")
    @api_version((1, 0), deprecate_in=(2, 0))
    def a() -> dict[str, str]:
        return {}

    aware = datetime(2025, 3, 1, 6, 0, tzinfo=timezone(timedelta(hours=5)))
    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=aware)},
    ).versionize()

    resp = TestClient(app).get("/v2_0/a")
    assert resp.headers["deprecation"] == f"@{int(aware.timestamp())}"


def test_sunset_before_deprecation_is_rejected_at_versionize() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/bad")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def bad() -> dict[str, str]:
        return {}  # pragma: no cover - versionize() raises before this route is mounted

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={
            (2, 0): VersionInfo(release_date=date(2026, 1, 1)),
            (3, 0): VersionInfo(release_date=date(2025, 1, 1)),
        },
    )
    with pytest.raises(ValueError, match="earlier than deprecate_in"):
        versioner.versionize()


def test_ordering_check_skipped_when_the_flag_is_off() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/bad")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def bad() -> dict[str, str]:
        return {"v": "1"}

    # Inverted dates, but deprecation_headers is off -> version_info is inert, no raise.
    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        version_info={
            (2, 0): VersionInfo(release_date=date(2026, 1, 1)),
            (3, 0): VersionInfo(release_date=date(2025, 1, 1)),
        },
    ).versionize()
    assert TestClient(app).get("/v2_0/bad").status_code == 200


def test_ordering_check_skipped_when_a_boundary_has_no_date() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/ok")
    @api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
    def ok() -> dict[str, str]:
        return {}

    # remove_in (3, 0) has no VersionInfo -> nothing to compare, must not raise.
    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2026, 1, 1))},
    ).versionize()
    assert TestClient(app).get("/v2_0/ok").status_code == 200


def test_ordering_check_skipped_for_a_route_without_both_boundaries() -> None:
    app = FastAPI()
    router = APIRouter()

    @router.get("/only-deprecate")
    @api_version((1, 0), deprecate_in=(2, 0))
    def only_deprecate() -> dict[str, str]:
        return {}

    RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        deprecation_headers=True,
        version_info={(2, 0): VersionInfo(release_date=date(2026, 1, 1))},
    ).versionize()
    assert TestClient(app).get("/v2_0/only-deprecate").status_code == 200


@pytest.mark.parametrize(
    "version_info",
    [
        pytest.param([(1, 0)], id="not-a-dict"),
        pytest.param({(1, 0): date(2025, 1, 1)}, id="value-not-a-versioninfo"),
        pytest.param({(1, 0): VersionInfo(release_date="2025-01-01")}, id="date-not-a-date"),
        pytest.param({(1, 0): VersionInfo(guide=123)}, id="guide-not-a-str"),
        pytest.param({(1, 0): VersionInfo(guide="https://x\r\nInjected: 1")}, id="guide-has-newline"),
        pytest.param({"2025": VersionInfo(release_date=date(2025, 1, 1))}, id="key-wrong-format"),
    ],
)
def test_invalid_version_info_rejected_at_construction(version_info: Any) -> None:
    # version_info is validated in __init__, before any route is read.
    with pytest.raises((TypeError, ValueError)):
        RouterVersioner(
            app=FastAPI(),
            routers=APIRouter(),
            version_format=VersionFormat.SEMVER,
            deprecation_headers=True,
            version_info=version_info,
        )
