from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import api_version

app = FastAPI()
router = APIRouter()


@router.get("/legacy")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def legacy_route():
    return {"msg": "I am stable in v1, deprecated in v2, gone in v3."}


@router.get("/current")
@api_version((3, 0))
def current_route():
    return {"msg": "I appear in v3."}


# --8<-- [start:snippet]
from datetime import date
from fastapi_router_versioning import RouterVersioner, VersionInfo

RouterVersioner(
    app=app,
    routers=router,
    deprecation_headers=True,
    version_info={
        (1, 0): VersionInfo(release_date=date(2024, 1, 15)),
        (2, 0): VersionInfo(
            release_date=date(2025, 3, 1),
            guide="https://api.example.com/docs/upgrade/v2",
        ),
        (3, 0): VersionInfo(release_date=date(2026, 1, 1)),
    },
).versionize()
# --8<-- [end:snippet]
