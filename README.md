# FastAPI Router Versioning

[![Build Status](https://github.com/mat81black/fastapi-router-versioning/workflows/Test/badge.svg)](https://github.com/mat81black/fastapi-router-versioning/actions)
[![codecov](https://codecov.io/github/mat81black/fastapi-router-versioning/graph/badge.svg?token=4WQ63Q7ESY)](https://codecov.io/github/mat81black/fastapi-router-versioning)
[![pypi package](https://img.shields.io/pypi/v/fastapi-router-versioning?color=%2334D058&label=pypi%20package)](https://pypi.org/project/fastapi-router-versioning/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/fastapi-router-versioning.svg?color=%2334D058)](https://pypi.org/project/fastapi-router-versioning/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Running multiple API versions side by side usually means duplicating routers, hand-rolling prefixes, or branching on request paths, and every one of those gets harder to maintain as versions pile up. `RouterVersioner` takes a declarative approach instead: annotate each route with the version it belongs to, and it generates the URL prefixes, the per-version OpenAPI schema, and the docs for you, without moving anything else in your app.

---

## Features

- **SemVer and CalVer**: version routes with `(major, minor)` tuples, or with arbitrary sortable strings
- **Per-version docs**: isolated Swagger UI, ReDoc, and `openapi.json` for every active version
- **Declarative lifecycle**: mark a route's introduction, deprecation, and removal with one decorator
- **Latest alias**: expose the newest version under a fixed `/latest` prefix clients can pin to
- **Self-hosted docs assets**: point Swagger UI and ReDoc at your own JS/CSS for air-gapped deployments
- **Reverse proxy and sub-app aware**: doc URLs pick up the ASGI `root_path` at request time
- **Configurable validation error status**: swap FastAPI's default `422` for any code, applied consistently to runtime responses and every OpenAPI schema, including the app's own root schema
- **Route composition support**: works across nested routers, WebSockets, `Depends`, and OpenAPI Callbacks

---

## Requirements

- Python ≥ 3.10
- FastAPI ≥ 0.120.0 (`0.137.0` and `0.137.1` are excluded: they shipped a routing internals rewrite before `iter_route_contexts()` landed in `0.137.2`, which this package relies on; supporting that narrow gap would have meant a third compatibility code path instead of the two the package actually needs)

---

## Installation

```bash
pip install fastapi-router-versioning
# or
uv add fastapi-router-versioning
```

---

## Quick start

`RouterVersioner` is not a request-time dependency, there's no `Depends()` involved. It's a
one-time setup step: you build it, then call `.versionize()` once, and it reads the routers
you gave it and mounts one copy per version. Attach `@api_version` to every route **before**
calling `.versionize()`, since that call is what reads the router and wires everything up;
routes added to the router afterward are never picked up.

### SemVer

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
# Docs at: /v1_0/docs, /v2_0/docs
```

### CalVer

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

CalVer tokens can be any string ("2025-01-01", "v3", "stable"...), but they are sorted
lexicographically to determine version order. ISO dates and zero-padded numbers (`"v01"`,
`"v02"`) sort correctly; unpadded strings like `"v1"`, `"v10"`, `"v2"` do not, and will place
routes under the wrong version.

---

## Route lifecycle

`deprecate_in` and `remove_in` describe when a route changes status, without needing a
separate route definition per version:

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
| v3.0    | no                | n/a                |

A route without `@api_version` isn't excluded, it falls back to `default_version`
(`(1, 0)` for SemVer, `"1"` for CalVer, unless overridden).

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
| `latest_prefix` | `str \| None` | `None` | If set, mounts an alias prefix (e.g. `"/latest"`) pointing to the newest version |
| `include_version_docs` | `bool` | `True` | Create per-version Swagger UI and ReDoc pages |
| `include_version_openapi_route` | `bool` | `True` | Create a per-version `openapi.json` route |
| `include_versions_route` | `bool` | `False` | Add a `GET /versions` endpoint listing all active versions |
| `sort_routes` | `bool` | `False` | Sort routes alphabetically by path within each version |
| `callback` | `Callable[[APIRouter, VersionT, str], None] \| None` | `None` | Called once per versioned router, right before it's included in the app |
| `webhook_routers` | `APIRouter \| list[APIRouter] \| None` | `None` | Router(s) with webhook definitions annotated via `@api_version`; each version's schema shows only the webhooks active in it |
| `openapi_hook` | `Callable[[dict, VersionT], dict] \| None` | `None` | Called with `(schema, version)` for each generated version schema; must return the (possibly modified) schema |
| `swagger_js_url` | `str \| None` | FastAPI CDN | Custom URL for the Swagger UI JS bundle |
| `swagger_css_url` | `str \| None` | FastAPI CDN | Custom URL for the Swagger UI CSS |
| `swagger_favicon_url` | `str \| None` | FastAPI favicon | Custom URL for the Swagger UI favicon |
| `redoc_js_url` | `str \| None` | FastAPI CDN | Custom URL for the ReDoc JS bundle |
| `redoc_favicon_url` | `str \| None` | FastAPI favicon | Custom URL for the ReDoc favicon |
| `redoc_with_google_fonts` | `bool` | `True` | Set `False` to stop ReDoc from loading Google Fonts |
| `validation_error_code` | `int` | `422` | Status code returned for request validation errors; also replaces the `422` entry everywhere it appears in the OpenAPI schema, root schema included |
| `handle_validation_exceptions` | `bool` | `True` | Set `False` to only patch the schema and register your own `RequestValidationError` handler |

`.versionize()` returns the list of versions it activated. It can only be called once per
instance; a second call raises `RuntimeError`, since it mutates the live FastAPI app in a way
that can't be undone.

---

## `@api_version` reference

```python
@api_version(version, *, deprecate_in=None, remove_in=None)
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `version` | `tuple[int, int] \| str` | yes | Version in which the route first appears |
| `deprecate_in` | same type \| `None` | no | Version from which the route is flagged deprecated in the docs |
| `remove_in` | same type \| `None` | no | Version from which the route stops being mounted |

`version`, `deprecate_in`, and `remove_in` must all match the `version_format` in use on
the `RouterVersioner` that will process the route (`tuple[int, int]` for SemVer, `str` for
CalVer).

---

## Advanced options

### Latest alias

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
).versionize()
# /latest/... now points at whichever version is currently highest
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

`prefix_format` and `semantic_version_format` control how a version renders in URLs and in
doc titles, independently of how it's expressed in `@api_version`. A common use is dropping
the minor number from the URL while still tracking it internally:

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
# Swagger titles read "v1", "v2" instead of "v1.0", "v2.0"
```

Routes are still decorated with `(major, minor)` tuples; only their URL and label change.

### OpenAPI schema hook

`openapi_hook` runs inside the per-version schema generation pipeline, so unlike patching
`app.openapi` yourself, it always receives the already-filtered schema for that specific
version:

```python
def my_openapi_hook(schema: dict, version: tuple[int, int]) -> dict:
    schema["info"]["x-logo"] = {"url": "https://example.com/logo.png"}

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

### OpenAPI Callbacks and Webhooks

Route-level **Callbacks** need no special handling: a `callbacks=[...]` argument on a route
is carried over to every versioned copy of it automatically:

```python
callback_router = APIRouter()

@callback_router.post("{$url}")
def on_event(body: dict) -> None: ...

@router.post("/items", callbacks=callback_router.routes)
@api_version((1, 0))
def create_item() -> dict: ...
```

**Webhooks** (`app.webhooks`) are visible in every version's schema by default. Pass
`webhook_routers` to version them the same way as regular routes, with `@api_version` on
each definition:

```python
webhook_router = APIRouter()

@webhook_router.post("/order-created")
@api_version((1, 0))
def webhook_order_v1(body: OrderV1) -> None: ...

@webhook_router.post("/order-created")
@api_version((2, 0))       # same path + method as v1: replaces it, doesn't add a second entry
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
# /v1_0/openapi.json lists: order-created (v1 payload), payment-failed
# /v2_0/openapi.json lists: order-created (v2 payload)   payment-failed is gone
```

A webhook version only becomes visible once a route version reaches that same prefix, since
both follow the same `remove_in` lifecycle.

### Multiple routers

```python
RouterVersioner(
    app=app,
    routers=[users_router, products_router],
    version_format=VersionFormat.SEMVER,
).versionize()
```

Both routers are versioned together, sharing the same prefix tree, so this is the way to
split a versioned API across modules without creating a second `RouterVersioner`.

### Self-hosted docs assets

Swagger UI and ReDoc load their JS/CSS from FastAPI's CDN by default. Point them at your own
copies for air-gapped or restricted-network deployments:

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

[`examples/download_static_assets.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/download_static_assets.py) downloads the required files in one step;
[`examples/self_hosted_docs_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/self_hosted_docs_app.py) wires them into a full app.

### Validation error status code

`validation_error_code` changes what FastAPI returns for a failed request body/query/path
validation, `422` by default, both at runtime and in the schema:

```python
RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
).versionize()
# Validation failures now return 400; every 422 entry in the schema becomes 400
```

Set `handle_validation_exceptions=False` to keep the schema change while writing your own
response body:

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
    handle_validation_exceptions=False,  # schema updated; the handler above owns the response
).versionize()
```

This also patches the app's own root `/docs`, `/redoc`, and `/openapi.json`, not just the
versioned ones, so there's nothing left showing the stale `422`.

Sharing one app across several `RouterVersioner` instances only makes sense for one reason:
mixing `version_format` values, SemVer for one group of routes and CalVer for another, on
the same app. Splitting modules that share a `version_format` doesn't need a second instance;
pass them all to one `RouterVersioner` via `routers=[...]` instead (see
[`multi_router_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/multi_router_app.py)).
If you do share an app across instances, two rules are enforced for you:

- Every instance with `handle_validation_exceptions=True` must agree on
  `validation_error_code`. FastAPI's exception handler is registered once per app, not per
  router, so a mismatch raises `RuntimeError` when the second instance is constructed rather
  than silently keeping whichever handler was registered first.
- Every instance needs its own `prefix_format`/`latest_prefix`. Two instances that resolve to
  the same prefix would otherwise overwrite each other's docs/openapi routes at the same
  path; this raises `RuntimeError` too.

For modules that genuinely don't need to coordinate at all, including a different
`validation_error_code` each, mount them as separate FastAPI sub-applications instead (next
section).

### Reverse proxy and sub-application mounting

The ASGI `root_path` FastAPI sets when an app runs behind a proxy or is mounted with
`app.mount()` is picked up automatically in every per-version doc URL:

```python
parent = FastAPI()
parent.mount("/api", app)  # root_path="/api" is injected per request
# /api/v1_0/docs correctly points at /api/v1_0/openapi.json
```

A mounted sub-application is a separate `FastAPI()` instance with its own `app.state`, so a
`RouterVersioner` attached to it is entirely independent from one attached to the parent, or
to another sub-application, no shared `validation_error_code`, no prefix coordination needed.
See [`examples/mounted_subapps_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/mounted_subapps_app.py).

### Callback hook

`callback` runs once per versioned router, right before `RouterVersioner` includes it in the
app, handy for logging every mount point or wiring metrics:

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

| File | What it shows |
|---|---|
| [`semver_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/semver_app.py) | Full SemVer lifecycle: introduce, deprecate, remove |
| [`calver_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/calver_app.py) | Same lifecycle, CalVer date strings instead |
| [`semver_major_only_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/semver_major_only_app.py) | Major-only URLs (`/v1`, `/v2`) via `prefix_format` |
| [`webhook_versioning_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/webhook_versioning_app.py) | Per-version webhook definitions via `webhook_routers` |
| [`multi_router_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/multi_router_app.py) | Several routers versioned together under one instance |
| [`self_hosted_docs_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/self_hosted_docs_app.py) | Swagger UI and ReDoc served from local static assets |
| [`openapi_hook_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/openapi_hook_app.py) | Per-version OpenAPI schema edits via `openapi_hook` |
| [`validation_error_code_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/validation_error_code_app.py) | `400` instead of `422`, handled automatically by `RouterVersioner` |
| [`validation_error_code_custom_handler_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/validation_error_code_custom_handler_app.py) | Same, but with `handle_validation_exceptions=False` and a custom handler |
| [`mounted_subapps_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/mounted_subapps_app.py) | Independently versioned modules as separate `app.mount()` sub-applications |

---

## Release Notes

[RELEASE_NOTES](https://github.com/mat81black/fastapi-router-versioning/blob/main/RELEASE_NOTES.md)

---

## License

[MIT](https://github.com/mat81black/fastapi-router-versioning/blob/main/LICENSE)
