"""
Self-hosted (air-gapped) docs example.

In air-gapped environments or corporate networks where CDN access is blocked,
serve Swagger UI and ReDoc assets from your own server instead of the default CDN.

Setup (one time):

    python examples/download_static_assets.py   # downloads assets to examples/static/
    pip install aiofiles                         # required by FastAPI StaticFiles

Then run:

    uvicorn examples.self_hosted_docs_app:app --reload
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Self-Hosted Docs API",
    description="Swagger UI and ReDoc served from local static assets — no CDN required.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def list_items() -> dict[str, list[str]]:
    return {"items": []}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    swagger_js_url="/static/swagger-ui-bundle.js",
    swagger_css_url="/static/swagger-ui.css",
    swagger_favicon_url="/static/favicon.png",
    redoc_js_url="/static/redoc.standalone.js",
    redoc_favicon_url="/static/favicon.png",
    redoc_with_google_fonts=False,  # avoids loading fonts.googleapis.com
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8005)
