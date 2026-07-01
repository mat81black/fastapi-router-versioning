"""
Multi-router example.

Shows how to version routes split across multiple APIRouters — the typical
real-world pattern where each domain (users, products, …) lives in its own
router/module. Pass them as a list to RouterVersioner and they are all
versioned together under a single prefix tree.
"""

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="Multi-Router API",
    description="Routes split across multiple routers and versioned together.",
)

users_router = APIRouter(prefix="/users", tags=["Users"])
products_router = APIRouter(prefix="/products", tags=["Products"])


class CreateProductRequest(BaseModel):
    name: str
    quantity: int


@users_router.get("/")
@api_version((1, 0))
def list_users() -> dict[str, list[str]]:
    return {"users": []}


@users_router.get("/profile")
@api_version((2, 0))
def user_profile() -> dict[str, str]:
    return {"profile": "extended profile added in v2.0"}


@products_router.get("/")
@api_version((1, 0))
def list_products() -> dict[str, list[str]]:
    return {"products": []}


@products_router.get("/search")
@api_version((2, 0))
def search_products() -> dict[str, list[str]]:
    return {"results": []}


# POST /products with an invalid "quantity" (e.g. "not-a-number") returns FastAPI's
# default 422 validation error.
@products_router.post("/")
@api_version((1, 0))
def create_product(body: CreateProductRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


versioner = RouterVersioner(
    app=app,
    routers=[users_router, products_router],  # list of routers versioned together
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8003)
