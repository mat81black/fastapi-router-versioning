"""
Custom versions dashboard via versions_dashboard_hook.

versions_dashboard_hook(version_models, root_path) -> str replaces the built-in dashboard
page entirely. Here it renders a Jinja template from examples/dashboard_assets/, with the
stylesheet kept as a separate file served from the same directory rather than inlined in
the page.

- version_models: the same list GET /versions returns under "versions". Each entry has
  "version" and, when the per-version docs exist, "swagger_url" / "redoc_url" /
  "openapi_url" (already root_path-prefixed).
- root_path: the request root_path ("" when there is none); used here only to build the
  stylesheet URL.

The hook is not handed the app title/version, so this one reads app.title and app.version
off the module-level app and passes them to the template, the way the built-in page does.

Setup:

    pip install jinja2

Run:

    uvicorn examples.versions_dashboard_hook_app:app --reload

then open http://127.0.0.1:8000/dashboard
"""

from pathlib import Path
from typing import Any

import jinja2

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

ASSETS_DIR = Path(__file__).parent / "dashboard_assets"

_templates = jinja2.Environment(
    loader=jinja2.FileSystemLoader(ASSETS_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
)

app = FastAPI(title="Dashboard Hook Demo")
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

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


def render_dashboard(version_models: list[dict[str, Any]], root_path: str) -> str:
    return _templates.get_template("versions_dashboard.html").render(
        versions=version_models,
        root_path=root_path,
        title=app.title,
        version=app.version,
    )


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    include_versions_dashboard=True,
    versions_dashboard_hook=render_dashboard,
)
versioner.versionize()
