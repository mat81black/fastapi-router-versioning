---
description: Return a custom status code for request validation errors in every version.
---

# Validation error status code

Changing FastAPI's default `422` for request validation errors is not something
`RouterVersioner` does itself: it's a separate, general-purpose concern, handled by the
[fastapi-validation-override](https://pypi.org/project/fastapi-validation-override/) package.
`openapi_hook` is the integration point: it lets you re-apply the same patch to every
per-version schema that `RouterVersioner` generates, so all of them, root schema included,
stay consistent.

```bash
uv add fastapi-validation-override
```

```python
--8<-- "docs_src/advanced/validation_error_status_code.py:snippet"
```

See [`examples/validation_override_integration_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/validation_override_integration_app.py).
