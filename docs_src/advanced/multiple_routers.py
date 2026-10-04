from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
users_router = APIRouter()
products_router = APIRouter()


@users_router.get("/users")
@api_version((1, 0))
def get_users():
    return {"users": []}


@products_router.get("/products")
@api_version((1, 0))
def get_products():
    return {"products": []}


# --8<-- [start:snippet]
RouterVersioner(
    app=app,
    routers=[users_router, products_router],
    version_format=VersionFormat.SEMVER,
).versionize()
# --8<-- [end:snippet]
