"""Builds the raster icons of docs/assets/images/ from the SVG logo.

    uv run --group screenshots python scripts/build_icons.py --channel chrome

The SVG files are the source: logo.svg, favicon.svg (the logo redrawn for small sizes) and
logo-header.svg are edited by hand. This script produces favicon.ico (16, 32 and 48 px),
favicon.png (the file the theme asks for) and apple-touch-icon.png from them.

Each icon is drawn at eight times its size and scaled down averaging each block of 8 x 8 pixels,
which is exact for a whole-number reduction. Drawing it straight at 16 or 64 px leaves
stair-stepped edges on the diagonals; a sharper filter such as Lanczos adds a halo around them.
"""

import argparse
import io
import struct

from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, sync_playwright

IMAGES = Path(__file__).parent.parent / "docs/assets/images"
SUPERSAMPLE = 8
ICO_SIZES = (16, 32, 48)


def square(favicon_svg: str) -> str:
    """The favicon without rounded corners, for iOS, which rounds them itself, and a little
    smaller inside, so the symbol doesn't touch the edge once it does."""
    assert 'rx="14"' in favicon_svg
    assert "scale(1.25)" in favicon_svg
    return favicon_svg.replace(' rx="14"', "").replace("scale(1.25)", "scale(1.1)")


def render(page: Page, svg: str, size: int) -> Image.Image:
    big = size * SUPERSAMPLE
    page.set_viewport_size({"width": big, "height": big})
    page.set_content(
        f'<body style="margin:0;background:transparent"><div style="width:{big}px;height:{big}px">{svg}</div></body>'
        f"<style>svg{{width:{big}px;height:{big}px;display:block}}</style>"
    )
    png = page.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": big, "height": big})
    return Image.open(io.BytesIO(png)).convert("RGBA").resize((size, size), Image.Resampling.BOX)


def write_ico(path: Path, images: list[Image.Image]) -> None:
    blobs = []
    for image in images:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        blobs.append(buffer.getvalue())
    offset = 6 + 16 * len(images)
    entries = b""
    for image, blob in zip(images, blobs, strict=True):
        entries += struct.pack("<BBBBHHII", image.width, image.height, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + entries + b"".join(blobs))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channel", help="installed browser to use: chrome or msedge (default: Playwright's Chromium)")
    args = parser.parse_args()

    favicon_svg = (IMAGES / "favicon.svg").read_text(encoding="utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel)
        page = browser.new_page()
        ico = [render(page, favicon_svg, size) for size in ICO_SIZES]
        favicon_png = render(page, favicon_svg, 64)
        touch = render(page, square(favicon_svg), 180)
        browser.close()

    write_ico(IMAGES / "favicon.ico", ico)
    favicon_png.save(IMAGES / "favicon.png", optimize=True)
    touch.convert("RGB").save(IMAGES / "apple-touch-icon.png", optimize=True)
    for name in ("favicon.ico", "favicon.png", "apple-touch-icon.png"):
        print(f"{name:22} {(IMAGES / name).stat().st_size:6} B")


if __name__ == "__main__":
    main()
