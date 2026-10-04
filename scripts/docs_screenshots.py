"""Regenerates the screenshots of docs/assets/screenshots/ from the apps the pages describe.

    uv run --group screenshots python scripts/docs_screenshots.py --channel chrome
    uv run --group screenshots python scripts/docs_screenshots.py --only swagger-v1 redoc-v2

Each screenshot is taken in a real browser, from an app that runs locally: the files of docs_src/
that the pages include, and the apps of examples/. Swagger UI and ReDoc load their scripts from a
CDN, so the machine needs network access.

--channel chrome (or msedge) uses the browser already installed. Without it, Playwright uses its
own Chromium, installed once with `uv run --group screenshots playwright install chromium`.
"""

import argparse
import importlib.util
import socket
import threading
import time

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import uvicorn

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).parent.parent
OUT = ROOT / "docs/assets/screenshots"
WIDTH = 800
REDOC_WIDTH = 1000  # ReDoc hides its side menu on narrower windows
SCALE = 2  # screenshots are taken at twice the size they are shown at, to stay sharp on dense screens
PADDING = 24


@dataclass(frozen=True)
class Shot:
    name: str
    app: str  # file with an `app`, relative to the repository root
    path: str
    kind: str  # "swagger" | "redoc" | "dashboard"


SHOTS = [
    Shot("swagger-v1", "examples/semver_app.py", "/v1_0/docs", "swagger"),
    Shot("swagger-v2", "examples/semver_app.py", "/v2_0/docs", "swagger"),
    Shot("redoc-v2", "examples/semver_app.py", "/v2_0/redoc", "redoc"),
    Shot("versions-dashboard", "examples/versions_dashboard_app.py", "/dashboard", "dashboard"),
    Shot("quickstart-semver-v1", "docs_src/quickstart/semver.py", "/v1_0/docs", "swagger"),
    Shot("quickstart-semver-v2", "docs_src/quickstart/semver.py", "/v2_0/docs", "swagger"),
    Shot("quickstart-calver", "docs_src/quickstart/calver.py", "/2025-01-01/docs", "swagger"),
    Shot("url-format-v1", "docs_src/advanced/custom_url_format.py", "/v1/docs", "swagger"),
    Shot("url-format-latest", "docs_src/advanced/custom_url_format.py", "/latest/docs", "swagger"),
    Shot("latest-alias", "docs_src/advanced/latest_alias.py", "/latest/docs", "swagger"),
    Shot("webhooks-v1", "examples/webhook_versioning_app.py", "/v1_0/docs", "swagger"),
    Shot("webhooks-v2", "examples/webhook_versioning_app.py", "/v2_0/docs", "swagger"),
]


def load_app(relative: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"shot_{relative.replace('/', '_')}", ROOT / relative)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


@contextmanager
def serve(app: Any) -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join()


def clip_for(page: Page, kind: str) -> dict[str, float]:
    """The part of the page to keep: from the top to the last thing worth showing."""
    if kind == "swagger":
        page.wait_for_selector(".swagger-ui .opblock")
        bottom = page.evaluate(
            "Math.max(...[...document.querySelectorAll('.opblock')].map(e => e.getBoundingClientRect().bottom + scrollY))"
        )
        return {"x": 0, "y": 30, "width": WIDTH, "height": bottom + PADDING - 30}
    if kind == "redoc":
        page.wait_for_selector(".menu-content")
        return {"x": 0, "y": 0, "width": REDOC_WIDTH, "height": 630}
    page.wait_for_selector("main ul li")
    box = page.evaluate(
        """() => {
            const r = document.querySelector('main').getBoundingClientRect();
            return {x: r.x, y: r.y, width: r.width, height: r.height};
        }"""
    )
    return {
        "x": box["x"] - PADDING,
        "y": box["y"] - PADDING,
        "width": box["width"] + 2 * PADDING,
        "height": box["height"] + 2 * PADDING,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channel", help="installed browser to use: chrome or msedge (default: Playwright's Chromium)")
    parser.add_argument("--only", nargs="+", metavar="NAME", help="take only these screenshots")
    args = parser.parse_args()

    shots = [shot for shot in SHOTS if not args.only or shot.name in args.only]
    unknown = set(args.only or []) - {shot.name for shot in SHOTS}
    if unknown:
        parser.error(f"unknown screenshot(s): {', '.join(sorted(unknown))}")

    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": 700}, device_scale_factor=SCALE, color_scheme="light"
        )
        page = context.new_page()
        for app_file in dict.fromkeys(shot.app for shot in shots):
            with serve(load_app(app_file)) as base_url:
                for shot in (s for s in shots if s.app == app_file):
                    page.set_viewport_size({"width": REDOC_WIDTH if shot.kind == "redoc" else WIDTH, "height": 700})
                    page.goto(f"{base_url}{shot.path}", wait_until="networkidle")
                    target = OUT / f"{shot.name}.jpg"
                    page.screenshot(path=target, type="jpeg", quality=88, clip=clip_for(page, shot.kind))
                    print(f"{shot.name:24} {target.stat().st_size // 1024:4} KB  <- {shot.app} {shot.path}")
        browser.close()


if __name__ == "__main__":
    main()
