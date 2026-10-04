---
description: Twelve runnable apps, one per feature of RouterVersioner.
---

# Examples

Every example is a complete, runnable app, and each one is imported and checked by the test suite. Run one with `uvicorn examples.<name>:app --reload` from a checkout of the repository.

## `semver_app.py`

Full SemVer lifecycle: introduce, deprecate, remove, permanent deprecation, multi-method route with partial takeover

??? example "Show the code"

    ```python
    --8<-- "examples/semver_app.py"
    ```

## `calver_app.py`

Introduce, deprecate and remove, with CalVer date strings instead of SemVer tuples

??? example "Show the code"

    ```python
    --8<-- "examples/calver_app.py"
    ```

## `semver_major_only_app.py`

Major-only URLs (`/v1`, `/v2`) via `prefix_format`

??? example "Show the code"

    ```python
    --8<-- "examples/semver_major_only_app.py"
    ```

## `deprecation_headers_app.py`

`Deprecation`, `Sunset` and `Link` response headers via `deprecation_headers` and `version_info`

??? example "Show the code"

    ```python
    --8<-- "examples/deprecation_headers_app.py"
    ```

## `webhook_versioning_app.py`

Per-version webhook definitions via `webhook_routers`

??? example "Show the code"

    ```python
    --8<-- "examples/webhook_versioning_app.py"
    ```

## `multi_router_app.py`

Several routers versioned together under one instance

??? example "Show the code"

    ```python
    --8<-- "examples/multi_router_app.py"
    ```

## `self_hosted_docs_app.py`

Swagger UI and ReDoc served from local static assets

??? example "Show the code"

    ```python
    --8<-- "examples/self_hosted_docs_app.py"
    ```

## `openapi_hook_app.py`

Per-version OpenAPI schema edits via `openapi_hook`

??? example "Show the code"

    ```python
    --8<-- "examples/openapi_hook_app.py"
    ```

## `versions_dashboard_app.py`

`GET /versions` JSON and the `GET /dashboard` HTML page side by side

??? example "Show the code"

    ```python
    --8<-- "examples/versions_dashboard_app.py"
    ```

## `versions_dashboard_hook_app.py`

Custom dashboard via `versions_dashboard_hook`: Jinja template with a separate stylesheet file

??? example "Show the code"

    ```python
    --8<-- "examples/versions_dashboard_hook_app.py"
    ```

## `mounted_subapps_app.py`

Independently versioned modules as separate `app.mount()` sub-applications

??? example "Show the code"

    ```python
    --8<-- "examples/mounted_subapps_app.py"
    ```

## `validation_override_integration_app.py`

Custom validation error status code via `fastapi-validation-override` and `openapi_hook`

??? example "Show the code"

    ```python
    --8<-- "examples/validation_override_integration_app.py"
    ```

## Support files

[`download_static_assets.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/download_static_assets.py) downloads the Swagger UI and ReDoc files used by `self_hosted_docs_app.py`, and the [`dashboard_assets/`](https://github.com/mat81black/fastapi-router-versioning/tree/main/examples/dashboard_assets) folder holds the template and stylesheet of `versions_dashboard_hook_app.py`.
