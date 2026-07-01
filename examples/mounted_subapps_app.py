"""
Sub-applications example.

Shows how to mount independently versioned modules as separate FastAPI
sub-applications via app.mount() — each with its own RouterVersioner, docs,
and OpenAPI schema. RouterVersioner already threads the ASGI root_path through
docs/openapi URLs automatically, so no extra configuration is needed.
"""

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


main_app = FastAPI(title="Main App")

# ── Admin sub-app: SemVer, validation errors return 400 ──────────────────────

admin_app = FastAPI(title="Admin API")
admin_router = APIRouter()


@admin_router.get("/users")
@api_version((1, 0))
def list_admin_users() -> dict[str, list[str]]:
    return {"users": []}


@admin_router.post("/items")
@api_version((1, 0))
def create_admin_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


RouterVersioner(
    app=admin_app, routers=admin_router, version_format=VersionFormat.SEMVER, validation_error_code=400
).versionize()


# ── Orders sub-app: CalVer ────────────────────────────────────────────────────

orders_app = FastAPI(title="Orders API")
orders_router = APIRouter()


@orders_router.get("/")
@api_version("2025-01-01")
def list_orders() -> dict[str, list[str]]:
    return {"orders": []}


@orders_router.post("/items")
@api_version("2025-01-01")
def create_order_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


RouterVersioner(app=orders_app, routers=orders_router, version_format=VersionFormat.CALVER).versionize()


# ── Mount both sub-apps on the main app ───────────────────────────────────────

main_app.mount("/admin", admin_app)
main_app.mount("/orders", orders_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(main_app, host="127.0.0.1", port=8009)
