---
description: Send Deprecation, Sunset and Link headers on routes in their deprecation window.
---

# Deprecation headers

By default the lifecycle is docs-only: a deprecated route is flagged in its per-version
OpenAPI, but a client calling it gets no signal. Set `deprecation_headers=True` and
`RouterVersioner` adds the `Deprecation`, `Sunset` and `Link` headers to every response of a
route in its deprecation window; `version_info` (one `VersionInfo` per version) supplies the
dates and guide URLs. Header values are computed once, at `versionize()` time. The only
per-request work is prefixing the `successor-version` link with the request's `root_path`,
exactly as the built-in `/docs` and `/openapi.json` routes do.

```python
--8<-- "docs_src/advanced/deprecation_headers.py:snippet"
```

| Header | Source | Emitted when |
|---|---|---|
| `Deprecation: @<unix-seconds>` ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745)) | `version_info[deprecate_in].release_date` | that version has a date |
| `Sunset: <HTTP-date>` ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594)) | `version_info[remove_in].release_date` | `remove_in` is set and that version has a date |
| `Link: …; rel="successor-version"` ([RFC 5829](https://www.rfc-editor.org/rfc/rfc5829)) | the next mounted version still serving the same `(path, method)`, `root_path`-prefixed | such a version exists |
| `Link: …; rel="deprecation"` (RFC 9745) | `version_info[deprecate_in].guide` | that version has a guide URL |

Both `VersionInfo` fields are optional; a version missing from the map, or a field left
`None`, just yields nothing for that part, with no warning. With `deprecation_headers=True`
and no `version_info` at all, only the `successor-version` link is emitted (it needs no
config). `versionize()` raises `ValueError` if a route's `remove_in` date precedes its
`deprecate_in` date (when both are dated): RFC 9745 forbids a `Sunset` earlier than the
`Deprecation`.

This adds nothing to `@api_version`: the lifecycle stays on the route, the dates stay on the
versioner. `Deprecation` and `Sunset` are only set if the response doesn't already carry them:
a route that sets its own keeps it. The `Link` field is sent alongside any the route already
emits (RFC 8288: multiple `Link` fields combine). See [`deprecation_headers_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/deprecation_headers_app.py).
