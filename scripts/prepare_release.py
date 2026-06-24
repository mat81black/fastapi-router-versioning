#!/usr/bin/env python3
"""Release helper: bumps __version__ in __init__.py.

Usage:
    python scripts/prepare_release.py prepare        # reads PREPARE_RELEASE_BUMP env
    python scripts/prepare_release.py current-version
"""
import os
import re
import sys
from pathlib import Path

VERSION_FILE = Path("fastapi_router_versioning/__init__.py")
VERSION_RE = re.compile(r'^__version__\s*=\s*["\'](.+)["\']', re.MULTILINE)


def _read_version() -> str:
    text = VERSION_FILE.read_text()
    m = VERSION_RE.search(text)
    if not m:
        sys.exit(f"Could not find __version__ in {VERSION_FILE}")
    return m.group(1)


def _write_version(new_version: str) -> None:
    text = VERSION_FILE.read_text()
    new_text = VERSION_RE.sub(f'__version__ = "{new_version}"', text)
    VERSION_FILE.write_text(new_text)


def _bump(version: str, bump: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"Unknown bump type: {bump!r}")


def cmd_prepare() -> None:
    bump = os.environ.get("PREPARE_RELEASE_BUMP", "").strip()
    if bump not in ("patch", "minor", "major"):
        sys.exit("PREPARE_RELEASE_BUMP must be patch, minor, or major")
    current = _read_version()
    new_version = _bump(current, bump)
    _write_version(new_version)
    print(f"Bumped {current} -> {new_version}")


def cmd_current_version() -> None:
    print(_read_version())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: prepare_release.py [prepare|current-version]")
    match sys.argv[1]:
        case "prepare":
            cmd_prepare()
        case "current-version":
            cmd_current_version()
        case _:
            sys.exit(f"Unknown command: {sys.argv[1]!r}")
