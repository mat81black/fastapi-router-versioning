---
description: Run a function once for each versioned router before it is mounted.
---

# Callback hook

`callback` runs for every versioned router, the `latest_prefix` alias included, right before
`RouterVersioner` includes it in the app, handy for logging every mount point or wiring metrics:

```python
--8<-- "docs_src/advanced/callback_hook.py:snippet"
```

If `versionize()` raises, don't catch the exception and retry. Errors found while the versions
are built, such as a callback that throws or two versions that resolve to the same prefix, are
raised before anything is added to the app, but the routers are then included one after another,
and this package makes no attempt to undo a partial inclusion. `versionize()` normally runs at
startup, so the app fails to start; fix the underlying issue and start it again.
