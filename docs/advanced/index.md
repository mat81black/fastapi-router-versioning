---
description: Deprecation headers, version discovery, hooks, self-hosted assets and other options of RouterVersioner.
---

# Advanced options

Everything here builds on the [Quick start](../quickstart.md) and the [route lifecycle](../lifecycle.md). Each option is a parameter of `RouterVersioner`; the full list is in the [reference](../reference.md).

- [Deprecation headers](deprecation-headers.md): `Deprecation`, `Sunset` and `Link` response headers on routes in their deprecation window
- [Latest alias](latest-alias.md): a fixed `/latest` prefix that points at the newest version
- [Version discovery](version-discovery.md): `GET /versions` and an HTML dashboard listing the active versions
- [Custom URL format](custom-url-format.md): change how a version appears in URLs and in the docs titles
- [OpenAPI schema hook](openapi-hook.md): edit the OpenAPI schema generated for each version
- [Validation error status code](validation-error-status-code.md): return a custom status code for request validation errors in every version
- [OpenAPI callbacks and webhooks](callbacks-and-webhooks.md): version webhook definitions, and carry route callbacks into every version
- [Multiple routers](multiple-routers.md): version several routers together, or share one app across instances
- [Self-hosted assets](self-hosted-assets.md): serve Swagger UI and ReDoc from your own files
- [Reverse proxy and sub-apps](reverse-proxy-and-sub-apps.md): `root_path` behind a proxy, and mounting sub-applications
- [Callback hook](callback-hook.md): run a function once for each versioned router before it is mounted
