from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="SemVer Lifecycle API",
    description="Demonstration of endpoint lifecycles using Semantic Versioning tuples.",
)

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


# 1. Introduced in v1.0, persists across all versions
@router.get("/persistent")
@api_version((1, 0))
def persistent_route() -> dict[str, str]:
    return {"status": "active", "message": "I persist across all versions."}


# 2. Added in v2.0
@router.get("/newcomer")
@api_version((2, 0))
def added_in_next_version() -> dict[str, str]:
    return {"status": "active", "message": "I was added in v2.0."}


# 3. Introduced in v1.0, deprecated in v2.0, removed in v3.0
@router.get("/lifecycle")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def lifecycle_route() -> dict[str, str]:
    return {
        "status": "active",
        "message": "I am stable in v1.0, deprecated in v2.0, and removed in v3.0.",
    }


# 4. Added in v3.0
@router.get("/future")
@api_version((3, 0))
def future_route() -> dict[str, str]:
    return {"status": "active", "message": "Welcome to v3.0!"}


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
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
