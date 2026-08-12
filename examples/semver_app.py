"""
SemVer lifecycle example.

Full endpoint lifecycle (introduce, deprecate, remove, permanent deprecation) plus a
multi-method route with a partial takeover, using Semantic Versioning tuples.

Run:

    uvicorn examples.semver_app:app --reload
"""

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(
    title="SemVer Lifecycle API",
    description="Demonstration of endpoint lifecycles using Semantic Versioning tuples.",
)

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


# 1. Introduced in v1.0, persists across all versions
@router.get("/persistent")
@api_version((1, 0))
def persistent_route() -> dict[str, str]:
    return {"status": "active", "message": "I persist across all versions."}


# 2. Added in v2.0
@router.get("/newcomer")
@api_version((2, 0))
def added_in_next_version() -> dict[str, str]:
    return {"status": "active", "message": "I was added in v2.0."}


# 3. Introduced in v1.0, deprecated in v2.0, removed in v3.0
@router.get("/lifecycle")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def lifecycle_route() -> dict[str, str]:
    return {
        "status": "active",
        "message": "I am stable in v1.0, deprecated in v2.0, and removed in v3.0.",
    }


# 4. Added in v3.0
@router.get("/future")
@api_version((3, 0))
def future_route() -> dict[str, str]:
    return {"status": "active", "message": "Welcome to v3.0!"}


# 5. Introduced in v1.0, deprecated in v2.0, with no remove_in: it stays deprecated forever,
# there's no removal planned.
@router.get("/legacy-notice")
@api_version((1, 0), deprecate_in=(2, 0))
def legacy_notice_route() -> dict[str, str]:
    return {"status": "deprecated", "message": "I was deprecated in v2.0, but I'm never removed."}


# 6. A single route handling both GET and POST from v1.0. In v2.0, a dedicated route takes
# over POST alone; GET keeps being served by this same handler in both versions.
# FastAPI warns about a duplicate operation ID for this route regardless of versioning
# (reproducible with plain FastAPI too); it's a cosmetic quirk of multi-method routes, safe
# to ignore here.
@router.api_route("/settings", methods=["GET", "POST"])
@api_version((1, 0))
def settings_route() -> dict[str, str]:
    return {"handler": "settings_v1", "message": "I handle both GET and POST."}


@router.post("/settings")
@api_version((2, 0))
def settings_post_v2() -> dict[str, str]:
    return {"handler": "settings_post_v2", "message": "I took over POST /settings from v2.0."}


# POST /items with an invalid "quantity" (e.g. "not-a-number") returns FastAPI's
# default 422 validation error.
@router.post("/items")
@api_version((1, 0))
def create_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()
