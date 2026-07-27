"""
Custom validation error status via fastapi-validation-override.

RouterVersioner does not have a built-in way to change FastAPI's default 422
status code: that is a separate, general-purpose concern handled by the
fastapi-validation-override package. This example wires the two together:

1. override_validation_error() patches the app once, at runtime and on its own
   root /openapi.json.
2. openapi_hook re-applies patch_422_responses() to the schema RouterVersioner
   generates for each version, so every versioned /vX_Y/openapi.json reflects
   the same status code too.
"""

from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi_validation_override import override_validation_error, patch_422_responses

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version

app = FastAPI(title="Validation Override Integration Demo")
router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items_v1(count: int) -> dict[str, str]:
    return {"count": str(count)}


@router.get("/items")
@api_version((2, 0))
def get_items_v2(count: int) -> dict[str, str]:
    return {"count": str(count)}


override_validation_error(app, status_code=400)


def versioning_openapi_hook(schema: dict[str, Any], version: VersionT) -> dict[str, Any]:
    return patch_422_responses(schema, "400")


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    openapi_hook=versioning_openapi_hook,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8010)
