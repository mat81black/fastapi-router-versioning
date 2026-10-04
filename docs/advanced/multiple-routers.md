---
description: Version several routers together, or share one app across several RouterVersioner instances.
---

# Multiple routers

```python
--8<-- "docs_src/advanced/multiple_routers.py:snippet"
```

Both routers are versioned together, sharing the same prefix tree, so this is the way to
split a versioned API across modules without creating a second `RouterVersioner`.

Sharing one app across several `RouterVersioner` instances only makes sense for one reason:
mixing `version_format` values, SemVer for one group of routes and CalVer for another, on
the same app. Splitting modules that share a `version_format` doesn't need a second instance;
pass them all to one `RouterVersioner` via `routers=[...]` instead (see
[`multi_router_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/multi_router_app.py)).
If you do share an app across instances, one rule is enforced: every instance needs
its own `prefix_format`/`latest_prefix`. Two instances that resolve to the same prefix would
otherwise overwrite each other's docs/openapi routes at the same path; this raises
`RuntimeError`. `/versions` (see [Version discovery](version-discovery.md))
doesn't need this coordination: every instance's contribution is aggregated into the same
endpoint automatically.

For modules that genuinely don't need to coordinate at all, mount them as separate FastAPI
sub-applications instead (see
[Reverse proxy and sub-apps](reverse-proxy-and-sub-apps.md)).
