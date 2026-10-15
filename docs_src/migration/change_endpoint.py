from fastapi import APIRouter, FastAPI
from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
router = APIRouter()


@router.get("/items")
def get_items():
    return {"items": ["a", "b"]}


# --8<-- [start:snippet]
@router.get("/items")
@api_version((2, 0))
def get_items_v2():
    return {"items": ["a", "b", "c"]}
# --8<-- [end:snippet]


app.include_router(router)

RouterVersioner(
    app=app, routers=router,
    version_format=VersionFormat.SEMVER
).versionize()
