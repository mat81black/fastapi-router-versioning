from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="Versioned Webhooks Demo",
    description="Demonstrates per-version webhook definitions using webhook_routers.",
)

# --- Regular routes ---

router = APIRouter()


@router.post("/orders")
@api_version((1, 0))
def create_order_v1() -> dict[str, str]:
    return {"version": "1.0", "status": "created"}


@router.post("/orders")
@api_version((2, 0))
def create_order_v2() -> dict[str, str]:
    return {"version": "2.0", "status": "accepted"}


@router.get("/items")
@api_version((1, 0))
def get_items() -> dict[str, object]:
    return {"items": ["a", "b"]}


# --- Webhook definitions ---
# Webhooks document outbound calls your API makes to subscriber URLs.
# Annotate them with @api_version just like regular routes.

webhook_router = APIRouter()


# Introduced in v1.0: basic order-created notification.
@webhook_router.post("/order-created")
@api_version((1, 0))
def on_order_created_v1(body: dict[str, str]) -> None:
    """
    Payload sent to subscribers when an order is created.

    v1 body: {"order_id": "...", "status": "created"}
    """


# v2.0 replaces the v1 definition (same path + method → only one entry per version).
# Subscribers on v2 receive an extended payload with the customer field.
@webhook_router.post("/order-created")
@api_version((2, 0))
def on_order_created_v2(body: dict[str, str]) -> None:
    """
    Payload sent to subscribers when an order is created.

    v2 body: {"order_id": "...", "status": "accepted", "customer_id": "..."}
    """


# Introduced in v1.0, removed in v2.0 (replaced by order-created).
@webhook_router.post("/payment-received")
@api_version((1, 0), remove_in=(2, 0))
def on_payment_received(body: dict[str, str]) -> None:
    """
    Fired when a payment is confirmed. Removed in v2 — subscribe to order-created instead.
    """


# --- Versionize ---

versioner = RouterVersioner(
    app=app,
    routers=router,
    webhook_routers=webhook_router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()

# Result:
#   /v1_0/openapi.json  → webhooks: /order-created (v1 payload), /payment-received
#   /v2_0/openapi.json  → webhooks: /order-created (v2 payload)   ← /payment-received removed

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8006)
