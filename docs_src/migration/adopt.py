from fastapi import APIRouter, FastAPI
from fastapi_router_versioning import RouterVersioner, VersionFormat

app = FastAPI()
router = APIRouter()


# --8<-- [start:routes]
@router.get("/items")
def get_items():
    return {"items": ["a", "b"]}


app.include_router(router)
# --8<-- [end:routes]

# --8<-- [start:versionize]
RouterVersioner(
    app=app, routers=router,
    version_format=VersionFormat.SEMVER
).versionize()
# --8<-- [end:versionize]
