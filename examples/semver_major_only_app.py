from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="SemVer Major-Only API",
    description="Demonstrates major-only versioning: /v1, /v2, /v3 instead of /v1_0, /v2_0.",
)

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


# 1. Introduced in v1, persists across all versions
@router.get("/persistent")
@api_version((1, 0))
def persistent_route() -> dict[str, str]:
    return {"status": "active", "message": "I persist across all versions."}


# 2. Added in v2
@router.get("/newcomer")
@api_version((2, 0))
def added_in_v2() -> dict[str, str]:
    return {"status": "active", "message": "I was added in v2."}


# 3. Introduced in v1, deprecated in v2, removed in v3
@router.get("/lifecycle")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def lifecycle_route() -> dict[str, str]:
    return {
        "status": "active",
        "message": "I am stable in v1, deprecated in v2, and removed in v3.",
    }


# 4. Added in v3
@router.get("/future")
@api_version((3, 0))
def future_route() -> dict[str, str]:
    return {"status": "active", "message": "Welcome to v3!"}


# POST /items with an invalid "quantity" (e.g. "not-a-number") returns FastAPI's
# default 422 validation error.
@router.post("/items")
@api_version((1, 0))
def create_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    prefix_format="/v{major}",
    semantic_version_format="{major}",
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
