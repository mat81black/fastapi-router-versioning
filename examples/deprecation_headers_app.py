"""
Runtime deprecation signalling example.

The declarative lifecycle (`deprecate_in` / `remove_in`) already flags routes as deprecated
in the per-version OpenAPI. Turn on `deprecation_headers=True` and `RouterVersioner` adds
RFC-conformant headers to every response of a route in its deprecation window. `version_info`,
one `VersionInfo` per version, supplies the dates and guide URLs:

    VersionInfo.release_date -> Deprecation (RFC 9745) at deprecate_in, Sunset (RFC 8594) at remove_in
    VersionInfo.guide        -> Link: <url>; rel="deprecation" (RFC 9745) at deprecate_in

Plus an automatic `Link: ...; rel="successor-version"` whenever a later version still serves
the same path. The header values are fixed at versionize() time (only the successor link's
root_path prefix is filled per request): no second decorator, no middleware, no `Depends()`.

Try:

    curl -i http://127.0.0.1:8000/v1_0/report   # not yet deprecated -> no headers
    curl -i http://127.0.0.1:8000/v2_0/report   # deprecated, removal dated -> Deprecation + Sunset
    curl -i http://127.0.0.1:8000/v3_0/report   # removed -> 404
    curl -i http://127.0.0.1:8000/v2_0/ping     # deprecated, no removal -> Deprecation + successor Link

Run:

    uvicorn examples.deprecation_headers_app:app --reload
"""

from datetime import date

from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionInfo, api_version

app = FastAPI(
    title="Deprecation Signalling API",
    description="Declarative lifecycle turned into RFC 9745 / RFC 8594 response headers.",
)

router = APIRouter()


# Stable across every version: never carries deprecation headers.
@router.get("/health")
@api_version((1, 0))
def health() -> dict[str, str]:
    return {"status": "ok"}


# Introduced in v1, deprecated in v2, removed in v3. The same handler serves it in v1 and v2
# (nothing replaces it), so v2 is a genuine deprecation window: responses there carry
# Deprecation (from version_info[(2, 0)].release_date), Sunset (from version_info[(3, 0)].
# release_date), and a Link to the v2 upgrade guide. No successor Link - the endpoint is
# being retired.
@router.get("/report")
@api_version((1, 0), deprecate_in=(2, 0), remove_in=(3, 0))
def report() -> dict[str, str]:
    return {"report": "flat, unpaginated"}


# Introduced in v1, deprecated in v2, never removed: it lives on in v3. From v2 its responses
# carry Deprecation, the v2 upgrade-guide Link, and a Link: rel="successor-version" pointing
# at /v3_0/ping. No Sunset - no removal is planned.
@router.get("/ping")
@api_version((1, 0), deprecate_in=(2, 0))
def ping() -> dict[str, str]:
    return {"pong": "still here"}


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    deprecation_headers=True,
    version_info={
        (1, 0): VersionInfo(release_date=date(2024, 1, 15)),
        (2, 0): VersionInfo(
            release_date=date(2025, 3, 1),
            guide="https://api.example.com/docs/upgrade/v2",
        ),
        (3, 0): VersionInfo(release_date=date(2026, 1, 1)),
    },
    latest_prefix="/latest",
    include_versions_route=True,
)
versioner.versionize()
