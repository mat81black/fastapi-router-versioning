from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


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


def test_webhook_routers_provided_but_empty_does_not_fall_back_to_app_webhooks() -> None:
    """Providing webhook_routers opts into per-version webhook control, even if that router
    currently defines no webhooks: it must not fall back to global app.webhooks, since that
    fallback is reserved for webhook_routers=None (not provided at all)."""
    app = FastAPI()

    @app.webhooks.post("/global-event")
    def global_webhook(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items() -> dict[str, str]: ...

    RouterVersioner(
        app=app,
        routers=router,
        webhook_routers=APIRouter(),
        version_format=VersionFormat.SEMVER,
    ).versionize()

    client = TestClient(app)
    schema_v1 = client.get("/v1_0/openapi.json").json()
    assert schema_v1.get("webhooks", {}) == {}


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
