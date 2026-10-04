from fastapi import APIRouter, FastAPI
from fastapi_router_versioning import (
    RouterVersioner, VersionFormat, api_version,
)

app = FastAPI()
router = APIRouter()


@router.get("/items")
@api_version("2025-01-01")
def get_items():
    return {"release": "2025-01-01"}


RouterVersioner(
    app=app, routers=router,
    version_format=VersionFormat.CALVER
).versionize()
