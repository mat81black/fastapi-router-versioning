# FastAPI Router Versioning

[![PyPI](https://img.shields.io/pypi/v/fastapi-router-versioning)](https://pypi.org/project/fastapi-router-versioning/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/fastapi-router-versioning)](https://pypi.org/project/fastapi-router-versioning/)

Router-based API versioning for FastAPI.

FastAPI has no built-in versioning mechanism. The common workaround — duplicating routers or managing prefixes manually — breaks down quickly as the number of versions grows. This package adds declarative versioning directly on routes, with isolated URL prefixes, per-version Swagger UI, and a full route lifecycle, without touching the existing application structure.

---

## Features

- **SemVer and CalVer** — version routes with `(major, minor)` tuples or arbitrary strings
- **Per-version docs** — isolated Swagger UI, ReDoc, and `openapi.json` for every version
- **Declarative lifecycle** — introduce, deprecate, and remove routes with a single decorator
- **Latest alias** — serve the newest version under a stable `/latest` prefix
- **Self-hosted docs** — point Swagger UI and ReDoc at your own assets for air-gapped environments
- **Reverse proxy aware** — doc URLs include the ASGI `root_path` at request time, so sub-app mounting works out of the box
- **Configurable validation error code** — return `400` (or any code) instead of `422` for request validation errors, with the OpenAPI schema updated automatically
- **Broad compatibility** — works with nested routers, WebSockets, `Depends`, and OpenAPI Callbacks

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

Each version gets its own Swagger UI at `/v1_0/docs`, `/v2_0/docs`, and so on.

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

Valid CalVer tokens: `"2025-01-01"`, `"v3"`, `"stable"`, etc.

**CalVer sorting:** versions are sorted lexicographically, so tokens must be comparable in the intended order. ISO dates (`"2025-01-01"`) and zero-padded numbers (`"v01"`, `"v02"`) work correctly. Non-padded strings like `"v1"`, `"v10"`, `"v2"` will not sort correctly and will cause routes to appear in the wrong versions.

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
| `webhook_routers` | `APIRouter \| list[APIRouter] \| None` | `None` | Router(s) containing webhook definitions annotated with `@api_version`; each version's schema shows only the webhooks active in that version |
| `openapi_hook` | `Callable[[dict, VersionT], dict] \| None` | `None` | Hook applied to the generated OpenAPI schema for each version; receives `(schema, version)` and must return the modified schema |
| `swagger_js_url` | `str \| None` | FastAPI CDN | Custom URL for the Swagger UI JS bundle |
| `swagger_css_url` | `str \| None` | FastAPI CDN | Custom URL for the Swagger UI CSS |
| `swagger_favicon_url` | `str \| None` | FastAPI favicon | Custom URL for the Swagger UI favicon |
| `redoc_js_url` | `str \| None` | FastAPI CDN | Custom URL for the ReDoc JS bundle |
| `redoc_favicon_url` | `str \| None` | FastAPI favicon | Custom URL for the ReDoc favicon |
| `redoc_with_google_fonts` | `bool` | `True` | If `False`, ReDoc will not load Google Fonts |
| `validation_error_code` | `int` | `422` | HTTP status code returned for request validation errors; also replaces the `422` entry in the OpenAPI schema |
| `handle_validation_exceptions` | `bool` | `True` | If `False`, only the schema is updated — register your own `RequestValidationError` handler to control the response body |

Call `.versionize()` after constructing the object. It returns the list of active versions.

---

## `@api_version` reference

```python
@api_version(version, *, deprecate_in=None, remove_in=None)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `version` | `tuple[int, int] \| str` | yes | First version in which this route is active |
| `deprecate_in` | same \| `None` | no | Version in which this route is marked deprecated in the docs |
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

Use `prefix_format` and `semantic_version_format` to control how versions appear in URLs and docs.

**Major-only versioning** (`/v1`, `/v2`, `/v3`):

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    prefix_format="/v{major}",
    semantic_version_format="{major}",
    latest_prefix="/latest",
).versionize()
# Mounts: GET /v1/items   GET /v2/items   GET /latest/items
# Swagger at /v1/docs, /v2/docs — titles show "v1", "v2"
```

The route decorator still uses `(major, minor)` tuples — only the URL and doc label change.

### OpenAPI schema hook

`openapi_hook` lets you modify the generated OpenAPI JSON for each version — useful for
custom extensions, logos, version-specific metadata, or AWS API Gateway integration.
Unlike overriding `app.openapi`, this hook is called inside the per-version generation
pipeline, so it receives the correct filtered schema.

```python
def my_openapi_hook(schema: dict, version: tuple[int, int]) -> dict:
    # Applied to every version
    schema["info"]["x-logo"] = {"url": "https://example.com/logo.png"}

    # Applied only to v1
    if version == (1, 0):
        schema["info"]["description"] += "\n\n**DEPRECATED:** Use v2."

    return schema

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    openapi_hook=my_openapi_hook,
).versionize()
```

The hook receives `(schema: dict, version: VersionT)` and must return the modified dict.

### OpenAPI Callbacks and Webhooks

**Callbacks** (per-route) are propagated automatically — any `callbacks=[...]` parameter
on a route is copied to every versioned copy of that route:

```python
callback_router = APIRouter()

@callback_router.post("{$url}")
def on_event(body: dict) -> None: ...

@router.post("/items", callbacks=callback_router.routes)
@api_version((1, 0))
def create_item() -> dict: ...
```

**Webhooks** (`app.webhooks`) appear in the OpenAPI schema of every version by default.
To version webhooks independently, use `webhook_routers` with the same `@api_version`
decorator used on regular routes:

```python
webhook_router = APIRouter()

@webhook_router.post("/order-created")
@api_version((1, 0))
def webhook_order_v1(body: OrderV1) -> None: ...

@webhook_router.post("/order-created")
@api_version((2, 0))       # replaces v1 definition (same path + method)
def webhook_order_v2(body: OrderV2) -> None: ...

@webhook_router.post("/payment-failed")
@api_version((1, 0), remove_in=(2, 0))
def webhook_payment_v1(body: dict) -> None: ...

RouterVersioner(
    app=app,
    routers=router,
    webhook_routers=webhook_router,
    version_format=VersionFormat.SEMVER,
).versionize()
# /v1_0/openapi.json → webhooks: /order-created (V1), /payment-failed
# /v2_0/openapi.json → webhooks: /order-created (V2)  ← /payment-failed removed
```

The same `remove_in` lifecycle applies. A new webhook version only appears once a route version creates that API prefix.

### Multiple routers

Pass a list of routers to version routes split across modules:

```python
RouterVersioner(
    app=app,
    routers=[users_router, products_router],
    version_format=VersionFormat.SEMVER,
).versionize()
```

All routers are versioned together under the same prefix tree.

### Self-hosted docs (air-gapped environments)

By default, Swagger UI and ReDoc assets are loaded from the FastAPI CDN. In air-gapped or corporate environments, point them at locally hosted assets:

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    swagger_js_url="/static/swagger-ui-bundle.js",
    swagger_css_url="/static/swagger-ui.css",
    swagger_favicon_url="/static/favicon.png",
    redoc_js_url="/static/redoc.standalone.js",
    redoc_favicon_url="/static/favicon.png",
    redoc_with_google_fonts=False,
).versionize()
```

See [`examples/download_static_assets.py`](examples/download_static_assets.py) for a script that downloads all required assets in one step, and [`examples/self_hosted_docs_app.py`](examples/self_hosted_docs_app.py) for a complete working example.

### Validation error code

By default FastAPI returns `422 Unprocessable Entity` for request validation errors.
Use `validation_error_code` to change the code returned both at runtime and in the OpenAPI schema:

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
).versionize()
# Validation errors now return 400; the schema shows 400 instead of 422
```

To keep full control over the response body, set `handle_validation_exceptions=False` and register your own handler:

```python
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def my_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"errors": exc.errors()})

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    handle_validation_exceptions=False,  # schema updated; handler is yours
).versionize()
```

**Multiple `RouterVersioner` instances sharing one app** (e.g. one per module in a modular
monolith) must all use the same `validation_error_code` when `handle_validation_exceptions=True`
— since FastAPI's exception handler is app-wide, not per-router, a mismatch raises
`RuntimeError` at construction time instead of silently picking whichever was registered
first. Each instance must also use a distinct `prefix_format`/`latest_prefix`, otherwise their
docs/openapi routes would collide at the same path — this also raises `RuntimeError`. See
[`examples/modular_monolith_two_versioners_app.py`](examples/modular_monolith_two_versioners_app.py).

### Reverse proxy / sub-app mounting

When the app runs behind a reverse proxy or is mounted as a sub-application, the ASGI `root_path` is included in all per-version doc URLs automatically — no extra configuration needed:

```python
parent = FastAPI()
parent.mount("/api", app)  # root_path="/api" is injected at request time
# /api/v1_0/docs correctly references /api/v1_0/openapi.json
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

---

## Examples

Runnable examples are available in the [`examples/`](examples/) directory:

| File | What it shows |
|---|---|
| [`semver_app.py`](examples/semver_app.py) | Full SemVer lifecycle (introduce, deprecate, remove) |
| [`calver_app.py`](examples/calver_app.py) | Same lifecycle with CalVer date strings |
| [`semver_major_only_app.py`](examples/semver_major_only_app.py) | Custom prefix `/v1`, `/v2` via `prefix_format` |
| [`webhook_versioning_app.py`](examples/webhook_versioning_app.py) | Per-version webhook definitions via `webhook_routers` |
| [`multi_router_app.py`](examples/multi_router_app.py) | Multiple routers versioned together |
| [`self_hosted_docs_app.py`](examples/self_hosted_docs_app.py) | Swagger UI and ReDoc from local static assets |
| [`validation_error_code_app.py`](examples/validation_error_code_app.py) | Return `400` instead of `422` for validation errors (automatic handler via `RouterVersioner`) |
| [`validation_error_code_custom_handler_app.py`](examples/validation_error_code_custom_handler_app.py) | Same, but with `handle_validation_exceptions=False` and a user-defined exception handler |
| [`modular_monolith_two_versioners_app.py`](examples/modular_monolith_two_versioners_app.py) | Two independent `RouterVersioner` instances (SemVer + CalVer) on one app, sharing the same `validation_error_code` |

---

## License

[MIT](LICENSE)
