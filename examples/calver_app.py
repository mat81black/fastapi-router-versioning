from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="CalVer Lifecycle API",
    description="Demonstration of endpoint lifecycles using Calendar Versioning strings.",
)

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


# 1. Introduced in the January release, persists across all versions
@router.get("/persistent")
@api_version("2025-01-01")
def persistent_route() -> dict[str, str]:
    return {"status": "active", "message": "I persist across all versions."}


# 2. Added in the June release
@router.get("/newcomer")
@api_version("2025-06-01")
def added_in_next_version() -> dict[str, str]:
    return {"status": "active", "message": "I was added in 2025-06-01."}


# 3. Introduced in January, deprecated in June, removed in December
@router.get("/lifecycle")
@api_version("2025-01-01", deprecate_in="2025-06-01", remove_in="2025-12-01")
def lifecycle_route() -> dict[str, str]:
    return {
        "status": "active",
        "message": "I am stable in Jan, deprecated in Jun, and removed in Dec.",
    }


# 4. Added in the December release
@router.get("/future")
@api_version("2025-12-01")
def future_route() -> dict[str, str]:
    return {"status": "active", "message": "Welcome to the December release!"}


# POST /items with an invalid "quantity" (e.g. "not-a-number") returns FastAPI's
# default 422 validation error.
@router.post("/items")
@api_version("2025-01-01")
def create_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.CALVER,
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
