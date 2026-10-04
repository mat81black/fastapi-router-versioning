from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


class OrderV1(BaseModel):
    order_id: int


class OrderV2(BaseModel):
    order_id: int
    total: float


app = FastAPI()
router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items_v1():
    return {"items": ["a", "b"]}


@router.get("/items")
@api_version((2, 0))
def get_items_v2():
    return {"items": ["a", "b", "c"]}


# --8<-- [start:snippet]
webhook_router = APIRouter()

@webhook_router.post("/order-created")
@api_version((1, 0))
def webhook_order_v1(body: OrderV1) -> None: ...

# Same path and method as v1: replaces it instead of adding a second entry
@webhook_router.post("/order-created")
@api_version((2, 0))
def webhook_order_v2(body: OrderV2) -> None: ...

@webhook_router.post("/payment-failed")
@api_version((1, 0), remove_in=(2, 0))
def webhook_payment_v1(body: dict) -> None: ...

RouterVersioner(
    app=app,
    routers=router,
    webhook_routers=webhook_router,
    version_format=VersionFormat.SEMVER,
).versionize()
# --8<-- [end:snippet]
