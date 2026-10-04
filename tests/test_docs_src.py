import importlib.util
import re

from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from fastapi_router_versioning._compat import iter_routes_flat

DOCS_SRC = Path(__file__).parent.parent / "docs_src"
SNIPPETS = sorted(DOCS_SRC.rglob("*.py"))


@pytest.mark.parametrize("snippet", SNIPPETS, ids=lambda path: path.relative_to(DOCS_SRC).with_suffix("").as_posix())
def test_docs_snippet_runs_and_serves_every_version_schema(snippet: Path) -> None:
    """The docs pages include these files, so a page can't show code that no longer runs.
    Importing the file versionizes its app; each version must then serve its own schema."""
    spec = importlib.util.spec_from_file_location(f"docs_src_{snippet.stem}", snippet)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    client = TestClient(module.app)
    schema_paths = [
        route.path
        for route in iter_routes_flat(module.app.routes)
        if route.path.endswith("/openapi.json") and route.path != "/openapi.json"
    ]

    assert schema_paths
    for path in schema_paths:
        assert client.get(path).status_code == 200, path


def pages_text() -> str:
    return "\n".join(page.read_text(encoding="utf-8") for page in (DOCS_SRC.parent / "docs").rglob("*.md"))


def test_every_docs_src_file_is_included_by_a_page() -> None:
    """A file no page includes is an example nobody reads, and nobody notices when it rots."""
    pages = pages_text()

    files = [path.relative_to(DOCS_SRC.parent).as_posix() for path in SNIPPETS]

    assert [path for path in files if path not in pages] == []


def test_every_page_include_points_at_an_existing_docs_src_file() -> None:
    included = re.findall(r'--8<-- "(docs_src/[^":]+)', pages_text())

    assert included
    assert [path for path in included if not (DOCS_SRC.parent / path).is_file()] == []
