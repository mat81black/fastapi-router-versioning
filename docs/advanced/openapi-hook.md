---
description: Edit the OpenAPI schema generated for each version.
---

# OpenAPI schema hook

`openapi_hook` runs inside the per-version schema generation pipeline, so unlike patching
`app.openapi` yourself, it always receives the already-filtered schema for that specific
version:

```python
--8<-- "docs_src/advanced/openapi_hook.py:snippet"
```
