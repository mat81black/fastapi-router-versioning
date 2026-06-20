"""
One-time setup script: downloads Swagger UI and ReDoc assets locally.

Run from the project root (requires internet access only this once):

    python examples/download_static_assets.py

After running, install the StaticFiles dependency and start the app:

    pip install aiofiles
    uvicorn examples.self_hosted_docs_app:app --reload
"""

import urllib.request

from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

ASSETS = {
    "swagger-ui-bundle.js": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
    "swagger-ui.css": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    "redoc.standalone.js": "https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js",
    "favicon.png": "https://fastapi.tiangolo.com/img/favicon.png",
}

for filename, url in ASSETS.items():
    dest = STATIC_DIR / filename
    print(f"Downloading {filename}...", end=" ", flush=True)
    urllib.request.urlretrieve(url, dest)
    print(f"done ({dest.stat().st_size // 1024} KB)")

print(f"\nAssets saved to {STATIC_DIR}")
print("Next steps:")
print("  pip install aiofiles")
print("  uvicorn examples.self_hosted_docs_app:app --reload")
