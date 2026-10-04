"""Generates README.md from the docs, so the two can't drift apart.

The README is the page PyPI and GitHub show. Its intro, features, requirements, installation and
first example come from docs/index.md, docs/quickstart.md and docs_src/quickstart/semver.py; the
logo, the badges and the closing links are written here.

    uv run python scripts/generate_readme.py

Like FastAPI's generate-readme, it rewrites README.md and exits with 1 when the file was out of
date, which is what makes the pre-commit hook fail once and pass after the change is staged.
"""

import re
import sys

from pathlib import Path

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
SITE_URL = "https://mat81black.github.io/fastapi-router-versioning/"
REPO_URL = "https://github.com/mat81black/fastapi-router-versioning"
ASSETS_URL = "https://raw.githubusercontent.com/mat81black/fastapi-router-versioning/main/docs/assets/images"

HEADER = f"""<p align="center">
  <img src="{ASSETS_URL}/logo.svg" alt="FastAPI Router Versioning logo" width="128" height="128">
</p>

<h1 align="center">
  <img src="{ASSETS_URL}/wordmark.png" alt="FastAPI Router Versioning" width="480">
</h1>

<p align="center">
  <a href="{REPO_URL}/actions"><img src="{REPO_URL}/workflows/Test/badge.svg" alt="Build Status"></a>
  <a href="https://codecov.io/github/mat81black/fastapi-router-versioning"><img src="https://codecov.io/github/mat81black/fastapi-router-versioning/graph/badge.svg?token=4WQ63Q7ESY" alt="codecov"></a>
  <a href="https://pypi.org/project/fastapi-router-versioning/"><img src="https://img.shields.io/pypi/v/fastapi-router-versioning?color=%2334D058&label=pypi%20package" alt="pypi package"></a>
  <a href="https://pypi.org/project/fastapi-router-versioning/"><img src="https://img.shields.io/pypi/pyversions/fastapi-router-versioning.svg?color=%2334D058" alt="Supported Python versions"></a>
  <a href="{REPO_URL}/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
</p>
"""

FOOTER = f"""## Release Notes

[RELEASE_NOTES]({REPO_URL}/blob/main/docs/release-notes.md)

---

## License

[MIT]({REPO_URL}/blob/main/LICENSE)
"""


def sections(markdown: str) -> dict[str, list[str]]:
    """The body of each `## ` section, without the blank lines around it. Headings inside code
    fences don't count."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        if not in_fence and line.startswith("## "):
            current = found.setdefault(line[3:].strip(), [])
        elif current is not None:
            current.append(line)
    return {title: _trim(lines) for title, lines in found.items()}


def _trim(lines: list[str]) -> list[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def intro(index: str) -> str:
    """The paragraph that follows the one-line description under the title."""
    lines = index.splitlines()
    tagline = next(i for i, line in enumerate(lines) if 'class="hero-tagline"' in line)
    return next(line for line in lines[tagline + 1 :] if line.strip())


def requirements(body: list[str]) -> str:
    """The bullets as they are, and the admonition as a quote: GitHub and PyPI don't render it."""
    out: list[str] = []
    lines = iter(body)
    for line in lines:
        admonition = re.match(r'!!! \w+ "(.+)"', line)
        if not admonition:
            out.append(line)
            continue
        text = _trim([rest[4:] for rest in lines])
        out += [f"> **{admonition.group(1)}**", ">", *(f"> {rest}" if rest else ">" for rest in text)]
    return "\n".join(out)


def installation(body: list[str]) -> str:
    """The commands of the pip and uv tabs, in one block."""
    commands = [line[4:] for line in body if line.startswith("    ") and not line.strip().startswith("```")]
    return "```bash\n" + "\n# or\n".join(commands) + "\n```"


def first_paragraph(markdown: str) -> str:
    body = markdown.split("---", 2)[2] if markdown.startswith("---") else markdown
    lines = [line for line in body.splitlines() if not line.startswith("# ")]
    paragraph: list[str] = []
    for line in _trim(lines):
        if not line.strip():
            break
        paragraph.append(line)
    return "\n".join(paragraph)


def generate_readme() -> str:
    index = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    quickstart = (ROOT / "docs/quickstart.md").read_text(encoding="utf-8")
    snippet = (ROOT / "docs_src/quickstart/semver.py").read_text(encoding="utf-8").rstrip("\n")
    parts = sections(index)

    return f"""{HEADER}
{intro(index)}

Documentation: {SITE_URL}

---

## Features

{chr(10).join(parts["Features"])}

---

## Requirements

{requirements(parts["Requirements"])}

---

## Installation

{installation(parts["Installation"])}

---

## Quick start

{first_paragraph(quickstart)}

```python
{snippet}
```

CalVer, the route lifecycle, the parameter reference and the advanced options are in the [documentation]({SITE_URL}).

---

{FOOTER}"""


def main() -> int:
    new_content = generate_readme()
    old_content = README.read_text(encoding="utf-8")
    if new_content != old_content:
        README.write_text(new_content, encoding="utf-8")
        print("README.md was out of date; it has been regenerated from the docs.")
        return 1
    print("README.md is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
