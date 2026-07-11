# Release Notes

## Latest Changes

## 0.2.6 (2026-07-11)

### Refactors

* ♻️ Use fastapi-native imports instead of importing from starlette directly. PR [#38](https://github.com/mat81black/fastapi-router-versioning/pull/38) by [@mat81black](https://github.com/mat81black).

## 0.2.5 (2026-07-10)

### Fixes

* 🐛 Fix misleading self-collision error in RouterVersioner prefix claiming. PR [#36](https://github.com/mat81black/fastapi-router-versioning/pull/36) by [@mat81black](https://github.com/mat81black).

## 0.2.4 (2026-07-09)

### Internal

* 🔧 Integrate Codecov for coverage tracking and update README. PR [#34](https://github.com/mat81black/fastapi-router-versioning/pull/34) by [@mat81black](https://github.com/mat81black).

## 0.2.3 (2026-07-09)

### Docs
* 📝 Rewrite README with PyPI-safe links and corrected project metadata. PR [#27](https://github.com/mat81black/fastapi-router-versioning/pull/27) by [@mat81black](https://github.com/mat81black).

### Internal

* ⬆ bump the python-packages group with 2 updates. PR [#30](https://github.com/mat81black/fastapi-router-versioning/pull/30) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ bump https://github.com/crate-ci/typos from v1.48.0 to 5.0.7 in the pre-commit group. PR [#29](https://github.com/mat81black/fastapi-router-versioning/pull/29) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ bump dorny/paths-filter from 4.0.1 to 4.0.2 in the github-actions group. PR [#31](https://github.com/mat81black/fastapi-router-versioning/pull/31) by [@dependabot[bot]](https://github.com/apps/dependabot).
* ⬆ bump fastapi from 0.138.1 to 0.139.0. PR [#32](https://github.com/mat81black/fastapi-router-versioning/pull/32) by [@dependabot[bot]](https://github.com/apps/dependabot).
* 🔧 Overhaul CI/CD workflows for labeling, releases, and coverage tracking. PR [#28](https://github.com/mat81black/fastapi-router-versioning/pull/28) by [@mat81black](https://github.com/mat81black).

## 0.2.2 (2026-07-01)

### Fixes

* 🐛 Fix root OpenAPI schema not reflecting validation_error_code. PR [#21](https://github.com/mat81black/fastapi-router-versioning/pull/21) by [@mat81black](https://github.com/mat81black).
* 🐛 Fix silent conflicts from misconfigured RouterVersioner instances sharing an app. PR [#20](https://github.com/mat81black/fastapi-router-versioning/pull/20) by [@mat81black](https://github.com/mat81black).

### Internal

* 👷 Add a regression test for `RouterVersioner` under a real `app.mount()` sub-application, and `examples/mounted_subapps_app.py` demonstrating the same scenario. PR [#22](https://github.com/mat81black/fastapi-router-versioning/pull/22) by [@mat81black](https://github.com/mat81black).

### Refactors

* ♻️ Reorder RouterVersioner methods to match their call graph. PR [#23](https://github.com/mat81black/fastapi-router-versioning/pull/23) by [@mat81black](https://github.com/mat81black).

## 0.2.1 (2026-06-26)

### Fixes

* 🐛 Fix `api_version` signature to enforce `deprecate_in` and `remove_in` as keyword-only arguments, aligning the implementation with the documented signature. PR [#18](https://github.com/mat81black/fastapi-router-versioning/pull/18) by [@mat81black](https://github.com/mat81black).

## 0.2.0 (2026-06-26)

### Features

* ✨ Add `validation_error_code` parameter to `RouterVersioner` to override the HTTP status code returned for request validation errors (default: `422`). The OpenAPI schema is updated automatically to reflect the custom code. PR [#16](https://github.com/mat81black/fastapi-router-versioning/pull/16) by [@mat81black](https://github.com/mat81black).
* ✨ Add `handle_validation_exceptions` parameter to `RouterVersioner`: when `False`, only the OpenAPI schema is updated, leaving the exception handler to the user. PR [#16](https://github.com/mat81black/fastapi-router-versioning/pull/16) by [@mat81black](https://github.com/mat81black).

### Fixes

* 🐛 Fix Python 3.14 classifier not actually added to `pyproject.toml` in 0.1.2. PR [#15](https://github.com/mat81black/fastapi-router-versioning/pull/15) by [@mat81black](https://github.com/mat81black).

## 0.1.2 (2026-06-25)

### Internal

* 👷 Add Python 3.14 classifier to `pyproject.toml` to align with the versions already covered by CI.

### Docs

* 📝 Update README and `pyproject.toml` to clarify package description and improve documentation consistency. PR [#12](https://github.com/mat81black/fastapi-router-versioning/pull/12) by [@mat81black](https://github.com/mat81black).

## 0.1.1 (2026-06-24)

### Features

* ✨ Add per-version OpenAPI schema caching: schemas are generated once and cached, reducing overhead on repeated requests. PR [#5](https://github.com/mat81black/fastapi-router-versioning/pull/5) by [@mat81black](https://github.com/mat81black).
* ✨ Track which routes belong to each version to invalidate the cache automatically when the route set changes. PR [#5](https://github.com/mat81black/fastapi-router-versioning/pull/5) by [@mat81black](https://github.com/mat81black).

### Fixes

* 🐛 Fix WebSocket routes not being handled correctly in `versioned_routers` when the cache was active. PR [#5](https://github.com/mat81black/fastapi-router-versioning/pull/5) by [@mat81black](https://github.com/mat81black).
* 🐛 Improve OpenAPI schema cache resilience: cache is now safely bypassed on unexpected errors instead of raising. PR [#5](https://github.com/mat81black/fastapi-router-versioning/pull/5) by [@mat81black](https://github.com/mat81black).

### Internal

* 👷 Add `prepare-release.yml` workflow and `scripts/prepare_release.py` for automated version bumping and release PR creation. PR [#6](https://github.com/mat81black/fastapi-router-versioning/pull/6) by [@mat81black](https://github.com/mat81black).
* 👷 Add `changes` job to `test.yml` and `test-redistribute.yml` to skip CI when no relevant files are modified. PR [#10](https://github.com/mat81black/fastapi-router-versioning/pull/10) by [@mat81black](https://github.com/mat81black).

## 0.1.0 (2025-06-24)

🚀 First official public release of **fastapi-router-versioning**.

Router-based API versioning for FastAPI, with declarative route lifecycle, per-version OpenAPI schemas, and isolated documentation — without altering the core application structure.

### Features

* ✨ SemVer & CalVer support: route versioning using `(major, minor)` tuples or lexicographically sortable arbitrary strings.
* ✨ Declarative route lifecycle: introduce, deprecate (`deprecate_in`), and remove (`remove_in`) routes across versions.
* ✨ Per-version documentation: isolated Swagger UI, ReDoc, and `openapi.json` for each active version.
* ✨ OpenAPI schema hook: modify the filtered schema per version via `openapi_hook`.
* ✨ Independent webhook versioning via `webhook_routers`, with propagation of per-route OpenAPI Callbacks.
* ✨ Latest-version alias: expose the highest active version under a stable configurable prefix.
* ✨ Self-hosted docs: full control over Swagger/ReDoc static assets and option to disable Google Fonts.
* ✨ Reverse proxy aware: resolves and injects the ASGI `root_path` at request time.
