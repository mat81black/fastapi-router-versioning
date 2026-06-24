# Release Notes

## Latest Changes

## 0.1.1 (2026-06-24)

### Features

* ✨ Add per-version OpenAPI schema caching: schemas are generated once and cached, significantly reducing overhead on repeated requests.
* ✨ Track which routes belong to each version to invalidate the cache automatically when the route set changes.

### Fixes

* 🐛 Fix WebSocket routes not being handled correctly in `versioned_routers` when the cache was active.
* 🐛 Improve OpenAPI schema cache resilience: cache is now safely bypassed on unexpected errors instead of raising.

### Internal

* 👷 Add `prepare-release.yml` workflow and `scripts/prepare_release.py` for automated version bumping and release PR creation.
* 👷 Add `changes` job to `test.yml` and `test-redistribute.yml` to skip CI when no relevant files are modified.

## 0.1.0 (2025-06-24)

🚀 First official public release of **fastapi-router-versioning**.

This library provides an elegant, native, router-based solution for **FastAPI API versioning**. It allows you to manage the entire lifecycle of your endpoints declaratively with a single decorator, automatically generating isolated schemas and documentation for every version without altering your core application structure.

### Features

* ✨ SemVer & CalVer support: route versioning using `(major, minor)` tuples or lexicographically sortable arbitrary strings (like ISO dates).
* ✨ Declarative route lifecycle: introduce, deprecate (`deprecate_in`), and remove (`remove_in`) routes across versions.
* ✨ Per-version documentation: isolated Swagger UI, ReDoc, and `openapi.json` for each active version.
* ✨ Advanced OpenAPI customization via `openapi_hook`: manipulate the filtered JSON schema per version (vendor extensions, custom logos, API Gateway integrations).
* ✨ Independent webhook versioning via `webhook_routers`, with native propagation of per-route OpenAPI Callbacks and WebSockets.
* ✨ Latest-version alias: expose the highest active version under a stable configurable prefix (e.g. `/latest`).
* ✨ Enterprise & air-gapped ready: full control over Swagger/ReDoc static assets and option to disable Google Fonts.
* ✨ Reverse proxy aware: dynamically resolves and injects the ASGI `root_path` at request time.
