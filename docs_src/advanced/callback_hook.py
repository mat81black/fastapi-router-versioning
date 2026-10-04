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
def on_version_created(router: APIRouter, version, prefix: str) -> None:
    print(f"Registered version {version} at {prefix}")

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    callback=on_version_created,
).versionize()
# --8<-- [end:snippet]
