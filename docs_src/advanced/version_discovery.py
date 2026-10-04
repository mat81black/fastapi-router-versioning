from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

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
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    include_versions_route=True,
).versionize()
# --8<-- [end:snippet]
