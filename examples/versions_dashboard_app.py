"""
Versions dashboard example.

Enables both discovery surfaces side by side:

- GET /versions      JSON list of every active version (include_versions_route)
- GET /dashboard     HTML page with the same versions and links to their docs
                     (include_versions_dashboard)

The dashboard works with or without the JSON route. Its path moves with
versions_dashboard_path, and versions_dashboard_hook(version_models, root_path) -> str
replaces the built-in page entirely if you want your own markup.

Run:

    uvicorn examples.versions_dashboard_app:app --reload

then open http://127.0.0.1:8000/dashboard
"""

from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI(title="Versions Dashboard Demo")

router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items_v1() -> dict[str, object]:
    return {"version": "1.0", "items": ["a", "b"]}


@router.get("/items")
@api_version((2, 0))
def get_items_v2() -> dict[str, object]:
    return {"version": "2.0", "items": ["a", "b", "c"]}


@router.get("/reports")
@api_version((2, 0))
def get_reports() -> dict[str, object]:
    return {"reports": []}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
    include_versions_route=True,
    include_versions_dashboard=True,
)
versioner.versionize()
