---
description: How RouterVersioner turns decorated routes into one mounted router per version, each with its own prefix and OpenAPI schema.
---

# How it works

`RouterVersioner` is a one-time setup step. When you call `.versionize()`, it reads the routers you gave it, works out which routes belong to each version, and builds one new router per version. Your own routers are not modified.

## 1. Reading the routes

`@api_version` only records `version`, `deprecate_in` and `remove_in` as attributes on the decorated function, and returns the function unchanged: there is no wrapper, so the signature FastAPI inspects stays the original one.

`.versionize()` then flattens the routers you passed, nested routers included, and reads those attributes from every route. A route without `@api_version` is placed at `default_version`.

## 2. Deciding what each version contains

Every version mentioned by any route, as `version`, `deprecate_in` or `remove_in`, becomes a version of the app. They are walked in ascending order, keeping a set of active routes keyed by path and HTTP method:

- At each version, the routes introduced there are added. A route that has the same path and method as one already active **replaces** it: this is how you change an endpoint, by declaring the new one at a higher version.
- Routes whose `remove_in` is that version are dropped, but only if they are still the active route for that path and method. A newer route that already took over is not evicted by the older one's `remove_in`.
- A route that is not removed stays active in every later version.

Because the key is the path *and* the method, one method of a route can be replaced while the others carry on, and a version that only removes routes still exists, with no routes at all if nothing else is active.

For [`semver_app.py`](https://github.com/mat81black/fastapi-router-versioning/blob/main/examples/semver_app.py) this gives:

| Version | Routes served |
|---|---|
| 1.0 | `persistent`, `lifecycle`, `legacy-notice`, `settings` (GET, POST), `items` (POST) |
| 2.0 | `persistent`, `newcomer`, `lifecycle` (deprecated), `legacy-notice` (deprecated), `settings` (GET, and POST from the new route), `items` (POST) |
| 3.0 | `persistent`, `newcomer`, `future`, `legacy-notice` (deprecated), `settings`, `items`; `lifecycle` is gone |

Versions are ordered as tuples under SemVer and as strings under CalVer, which is why [CalVer strings must sort lexicographically](quickstart.md#calver).

## 3. Building one router per version

For each version, a new `APIRouter` is created with that version's prefix, built from `prefix_format` (for example `/v1_0`). Each active route is copied onto it with the options it was declared with, such as `response_model`, `dependencies` and `tags`, and with the custom route class it used, if any. A route that was partly replaced keeps only the methods still assigned to it in that version.

A route is marked `deprecated` in the versions at or after its `deprecate_in`, on top of a `deprecated=True` it already had. WebSocket routes are copied too, but have no OpenAPI entry to flag.

Two versions that resolve to the same prefix raise a `RuntimeError`, and so does a prefix already used by another `RouterVersioner` on the same app.

## 4. Documentation for each version

The same router also gets three routes, named after the app's own `openapi_url`, `docs_url` and `redoc_url`, so a version serves `/v1_0/openapi.json`, `/v1_0/docs` and `/v1_0/redoc`. `include_version_docs` and `include_version_openapi_route` switch them off.

Each version's OpenAPI schema is generated from that router's routes only, which is why a version lists just its own endpoints. It carries the app's metadata, with the version added to the title (`FastAPI - v1.0`) and as the schema version. It is generated on first request and cached, and if you set `openapi_hook` it is called with the schema and the version before caching.

With `webhook_routers`, a version shows the newest webhook set at or below it, using the same rules as routes. Without it, every version inherits `app.webhooks` unchanged.

## 5. Mounting

The versions are all built first. Only then are the prefixes claimed and the routers included in the app, followed by the `/versions` endpoint and the dashboard if you enabled them. The `latest_prefix` alias is one more router, built from the newest version's routes.

Since this happens once, a `RouterVersioner` can't be reused: call `.versionize()` a second time and it raises `RuntimeError`. If it raises for any reason, discard the app instead of retrying; see [Callback hook](advanced/callback-hook.md).

## What happens per request

The routes are ordinary FastAPI routes, and FastAPI handles the requests. This package adds two things at request time:

- The documentation, `openapi.json`, `/versions` and dashboard routes read the request's `root_path`, so the URLs they return are right behind a proxy or when the app is mounted as a sub-application.
- With `deprecation_headers=True`, routes in their deprecation window add the headers to their responses. The values are computed once, at `.versionize()` time; only the `root_path` in the `successor-version` link is filled in per request.
