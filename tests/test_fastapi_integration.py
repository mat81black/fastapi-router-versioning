from fastapi import APIRouter, Depends, FastAPI, Header, Request
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


def dummy_dependency(request: Request, user_agent: str = Header(default="test-agent")):
    return f"Injected: {user_agent}"


def test_dependency_injection_is_preserved():
    """Versioner must not alter the endpoint signature — FastAPI's Depends resolution must still work."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/items")
    @api_version((1, 0))
    def get_items(dep: str = Depends(dummy_dependency)):
        return {"result": dep}

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
    )
    versioner.versionize()

    client = TestClient(app)

    response = client.get("/v1_0/items", headers={"user-agent": "custom-agent"})

    assert response.status_code == 200
    assert response.json() == {"result": "Injected: custom-agent"}


def test_nested_routers_handling():
    """iter_route_contexts propagates parent/child prefixes, so paths include all segments."""
    app = FastAPI()
    parent_router = APIRouter(prefix="/api")
    child_router = APIRouter(prefix="/users")

    @child_router.get("/{user_id}")
    @api_version((1, 0))
    def get_user_v1(user_id: int):
        return {"user": user_id, "v": 1}

    @child_router.get("/{user_id}")
    @api_version((2, 0))
    def get_user_v2(user_id: int):
        return {"user": user_id, "v": 2}

    parent_router.include_router(child_router)

    versioner = RouterVersioner(
        app=app,
        routers=parent_router,
        version_format=VersionFormat.SEMVER,
    )
    versioner.versionize()

    client = TestClient(app)

    # The full path is /v{M}_{m}/api/users/{id} — both router prefixes are preserved.
    response_v1 = client.get("/v1_0/api/users/42")
    assert response_v1.status_code == 200
    assert response_v1.json() == {"user": 42, "v": 1}

    response_v2 = client.get("/v2_0/api/users/42")
    assert response_v2.status_code == 200
    assert response_v2.json() == {"user": 42, "v": 2}


def test_openapi_operation_id_uniqueness():
    """Two versioned endpoints sharing a function name must produce unique operationIds in OpenAPI."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0))
    def get_data(): ...

    @router.get("/data")
    @api_version((2, 0))
    def get_data():  # noqa: F811 — intentional redefinition to test operationId uniqueness
        ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
    )
    versioner.versionize()

    client = TestClient(app)

    response = client.get("/openapi.json")
    assert response.status_code == 200
    openapi_schema = response.json()

    operation_ids = []
    for paths in openapi_schema["paths"].values():
        for method in paths.values():
            operation_ids.append(method["operationId"])

    assert len(operation_ids) == len(set(operation_ids)), f"Duplicate operationIds found: {operation_ids}"
