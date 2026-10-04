from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
router = APIRouter()


# --8<-- [start:snippet]
@router.get("/legacy")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def legacy_route():
    return {"msg": "I am stable in v1, deprecated in v2, gone in v3."}
# --8<-- [end:snippet]

RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()
