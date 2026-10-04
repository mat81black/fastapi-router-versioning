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


RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()


# --8<-- [start:snippet]
parent = FastAPI()
parent.mount("/api", app)  # root_path="/api" is injected per request
# /api/v1_0/docs correctly points at /api/v1_0/openapi.json
# --8<-- [end:snippet]
