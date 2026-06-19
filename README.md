# fastapi-router-versioning

[![PyPI](https://img.shields.io/pypi/v/fastapi-router-versioning)](https://pypi.org/project/fastapi-router-versioning/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/fastapi-router-versioning)](https://pypi.org/project/fastapi-router-versioning/)

Native, router-based API versioning for FastAPI — with no extra dependencies.

---

## Features

- **Zero extra dependencies** — only FastAPI itself is required
- **SemVer and CalVer** — version routes with `(major, minor)` tuples or arbitrary strings
- **Per-version docs** — isolated Swagger UI, ReDoc, and `openapi.json` for every version
- **Declarative lifecycle** — introduce, deprecate, and remove routes with a single decorator
- **Latest alias** — serve the newest version under a stable `/latest` prefix
- **Broad compatibility** — works with nested routers, WebSockets, and `Depends`

---

## Requirements

- Python ≥ 3.10
- FastAPI ≥ 0.120.0

---

## Installation

```bash
pip install fastapi-router-versioning
# or
uv add fastapi-router-versioning
```

---

## Quick start — SemVer

```python
from fastapi import APIRouter, FastAPI
from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items_v1():
    return {"version": "1.0", "items": ["a", "b"]}


@router.get("/items")
@api_version((2, 0))
def get_items_v2():
    return {"version": "2.0", "items": ["a", "b", "c"]}


RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()
# Mounts: GET /v1_0/items   GET /v2_0/items
```

Each version also gets its own Swagger UI at `/v1_0/docs`, `/v2_0/docs`, and so on.

---

## Quick start — CalVer

```python
from fastapi import APIRouter, FastAPI
from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
router = APIRouter()


@router.get("/items")
@api_version("2025-01-01")
def get_items():
    return {"release": "2025-01-01"}


RouterVersioner(app=app, routers=router, version_format=VersionFormat.CALVER).versionize()
# Mounts: GET /2025-01-01/items
```

Any string is a valid CalVer token: `"2025-01-01"`, `"v3"`, `"stable"`, etc.

---

## Route lifecycle

Use `deprecate_in` and `remove_in` to manage the full lifecycle of a route across versions.

```python
@router.get("/legacy")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def legacy_route():
    return {"msg": "I am stable in v1, deprecated in v2, gone in v3."}
```

| Version | `/legacy` present? | Marked deprecated? |
|---------|-------------------|--------------------|
| v1.0    | yes               | no                 |
| v2.0    | yes               | **yes**            |
| v3.0    | **no**            | —                  |

Routes without `@api_version` fall back to `default_version` (default: `(1, 0)` for SemVer, `"1"` for CalVer).

---

## `RouterVersioner` reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `app` | `FastAPI` | required | The FastAPI application instance |
| `routers` | `APIRouter \| list[APIRouter]` | required | Router(s) whose routes will be versioned |
| `version_format` | `VersionFormat` | `SEMVER` | Versioning strategy (`SEMVER` or `CALVER`) |
| `prefix_format` | `str \| None` | `/v{major}_{minor}` / `/{version}` | URL prefix template; supports `{major}`, `{minor}`, `{version}` |
| `semantic_version_format` | `str \| None` | `{major}.{minor}` / `{version}` | Version label used in Swagger/ReDoc titles |
| `default_version` | `VersionT \| None` | `(1, 0)` / `"1"` | Fallback version for routes without `@api_version` |
| `latest_prefix` | `str \| None` | `None` | If set, adds an alias prefix (e.g. `"/latest"`) pointing to the newest version |
| `include_version_docs` | `bool` | `True` | Create per-version Swagger UI and ReDoc pages |
| `include_version_openapi_route` | `bool` | `True` | Create a per-version `openapi.json` route |
| `include_versions_route` | `bool` | `False` | Add a `GET /versions` endpoint listing all active versions |
| `sort_routes` | `bool` | `False` | Sort routes alphabetically by path within each version |
| `callback` | `Callable[[APIRouter, VersionT, str], None] \| None` | `None` | Hook called once per versioned router, before it is included in the app |

Call `.versionize()` after constructing the object. It returns the list of active versions.

---

## `@api_version` reference

```python
@api_version(version, *, deprecate_in=None, remove_in=None)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `version` | `tuple[int, int] \| str` | yes | Version when this route is introduced |
| `deprecate_in` | same \| `None` | no | Version when this route is marked deprecated in the docs |
| `remove_in` | same \| `None` | no | Version from which this route is removed entirely |

All three parameters must match the `version_format` configured on `RouterVersioner`
(`tuple[int, int]` for SemVer, `str` for CalVer).

---

## Advanced options

### Latest alias

Serve the newest version under a stable prefix that clients can pin to:

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
).versionize()
# Also mounts /latest/... pointing to the highest version
```

### Version discovery endpoint

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    include_versions_route=True,
).versionize()
```

```json
GET /versions
{
  "versions": [
    {
      "version": "1.0",
      "openapi_url": "/v1_0/openapi.json",
      "swagger_url": "/v1_0/docs",
      "redoc_url": "/v1_0/redoc"
    }
  ]
}
```

### Custom URL format

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    prefix_format="/api/v{major}",
    semantic_version_format="v{major}.{minor}",
).versionize()
# Mounts /api/v1/...  with docs titled "v1.0"
```

### Callback hook

Run custom logic each time a versioned router is created — useful for logging or metrics:

```python
def on_version_created(router: APIRouter, version, prefix: str) -> None:
    print(f"Registered version {version} at {prefix}")

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    callback=on_version_created,
).versionize()
```

### Multiple routers

```python
RouterVersioner(
    app=app,
    routers=[users_router, items_router],
    version_format=VersionFormat.SEMVER,
).versionize()
```

---

## License

[MIT](LICENSE)
