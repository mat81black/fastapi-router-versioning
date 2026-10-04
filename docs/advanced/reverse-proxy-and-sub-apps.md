---
description: How root_path is handled behind a proxy and when mounting sub-applications.
---

# Reverse proxy and sub-apps

The ASGI `root_path` FastAPI sets when an app runs behind a proxy or is mounted with
`app.mount()` is picked up automatically in every per-version doc URL:

```python
--8<-- "docs_src/advanced/reverse_proxy.py:snippet"
```

A mounted sub-application is a separate `FastAPI()` instance, so a `RouterVersioner` attached to
it is entirely independent from one attached to the parent, or to another sub-application, with
no prefix coordination needed.
See [`examples/mounted_subapps_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/mounted_subapps_app.py).
