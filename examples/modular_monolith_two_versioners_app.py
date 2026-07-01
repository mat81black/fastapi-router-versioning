"""
Modular monolith example: two independent RouterVersioner instances on one app.

Different modules can evolve on independent version cadences. Here:

- ``admin_router`` is a mature, low-churn module versioned with **SemVer**
  ((major, minor) tuples) under the ``/admin`` prefix.
- ``orders_router`` is a fast-moving module versioned with **CalVer**
  (ISO date strings) under the ``/orders`` prefix.

Each module gets its own ``RouterVersioner`` because ``version_format``,
``prefix_format``, and lifecycle cadence are module-level concerns.

``validation_error_code`` is different: it is an HTTP-level contract for the
*whole application* ("this API returns 400, not 422, for malformed requests"),
not a per-module setting. Both versioners below pass the **same** value
(``400``) on purpose. Passing different codes on two versioners sharing the same
app now raises ``RuntimeError`` at construction time instead of silently picking
whichever was registered first — always keep this value identical across every
RouterVersioner attached to the same app.

``latest_prefix`` must also be distinct per module (``/admin/latest`` vs.
``/orders/latest`` below): reusing the same alias across versioners raises
``RuntimeError`` too, since both would otherwise register colliding docs/openapi
routes at the exact same path.
"""

from pydantic import BaseModel

from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="Modular Monolith API",
    description="Two independently versioned modules sharing one FastAPI app.",
)


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


# ── Admin module: mature, versioned with SemVer ──────────────────────────────

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@admin_router.get("/users")
@api_version((1, 0))
def list_admin_users() -> dict[str, list[str]]:
    return {"users": []}


@admin_router.get("/audit-log")
@api_version((2, 0))
def audit_log() -> dict[str, list[str]]:
    return {"entries": []}


# POST /admin/items with an invalid "quantity" returns 400 (validation_error_code below).
@admin_router.post("/items")
@api_version((1, 0))
def create_admin_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


# ── Orders module: fast-moving, versioned with CalVer ────────────────────────

orders_router = APIRouter(prefix="/orders", tags=["Orders"])


@orders_router.get("/")
@api_version("2025-01-01")
def list_orders() -> dict[str, list[str]]:
    return {"orders": []}


@orders_router.get("/export")
@api_version("2025-06-01")
def export_orders() -> dict[str, str]:
    return {"status": "export scheduled"}


# POST /orders/items with an invalid "quantity" returns 400 too — same code as /admin,
# because validation_error_code is an app-wide contract, not a per-module setting.
@orders_router.post("/items")
@api_version("2025-01-01")
def create_order_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


# Same validation_error_code=400 on both: it's an app-wide HTTP contract,
# not something that should vary per module. Distinct latest_prefix per module
# avoids colliding docs/openapi routes.
RouterVersioner(
    app=app,
    routers=admin_router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    latest_prefix="/admin/latest",
).versionize()

RouterVersioner(
    app=app,
    routers=orders_router,
    version_format=VersionFormat.CALVER,
    validation_error_code=400,
    latest_prefix="/orders/latest",
).versionize()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8009)
