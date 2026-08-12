import importlib.util

from collections.abc import Iterator
from pathlib import Path

import pytest

from fastapi import FastAPI

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
EXAMPLE_FILES = sorted(path for path in EXAMPLES_DIR.glob("*.py") if path.name != "download_static_assets.py")

# semver_app.py's /settings route intentionally uses methods=["GET", "POST"] on a single
# function; FastAPI's own operation ID generator collides on that pattern regardless of
# versioning (reproducible with plain FastAPI too, see the comment in semver_app.py).
EXPECTED_WARNINGS = {"semver_app": "Duplicate Operation ID"}


@pytest.fixture(scope="module", autouse=True)
def _ensure_static_assets_dir() -> Iterator[None]:
    # self_hosted_docs_app.py mounts StaticFiles(directory=examples/static), which raises at
    # construction time if the directory doesn't exist. The real assets are only ever created
    # by running download_static_assets.py (a network call); an empty directory is enough here
    # since this test never serves a file from it.
    static_dir = EXAMPLES_DIR / "static"
    created = not static_dir.exists()
    if created:
        static_dir.mkdir()
    yield
    if created:
        static_dir.rmdir()


@pytest.mark.parametrize("example_file", EXAMPLE_FILES, ids=lambda path: path.stem)
def test_example_imports_and_generates_openapi_schema(example_file: Path) -> None:
    spec = importlib.util.spec_from_file_location(example_file.stem, example_file)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    apps = [value for value in vars(module).values() if isinstance(value, FastAPI)]
    assert apps, f"{example_file.name} does not define any FastAPI instance"

    expected_warning = EXPECTED_WARNINGS.get(example_file.stem)
    for app in apps:
        if expected_warning:
            with pytest.warns(UserWarning, match=expected_warning):
                schema = app.openapi()
        else:
            schema = app.openapi()
        assert isinstance(schema, dict)
        assert "paths" in schema
