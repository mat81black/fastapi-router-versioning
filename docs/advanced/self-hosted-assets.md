---
description: Serve Swagger UI and ReDoc from your own JS and CSS files.
---

# Self-hosted assets

Swagger UI and ReDoc load their JS/CSS from FastAPI's CDN by default. Point them at your own
copies for air-gapped or restricted-network deployments:

```python
--8<-- "docs_src/advanced/self_hosted_assets.py:snippet"
```

[`examples/download_static_assets.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/download_static_assets.py) downloads the required files in one step;
[`examples/self_hosted_docs_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/self_hosted_docs_app.py) wires them into a full app.
