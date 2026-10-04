from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

app = FastAPI()
router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items_v1():
    return {"items": ["a", "b"]}


@router.get("/items")
@api_version((2, 0))
def get_items_v2():
    return {"items": ["a", "b", "c"]}


@router.get("/items/{item_id}")
@api_version((1, 0))
def get_item(item_id: int):
    return {"item_id": item_id}


# --8<-- [start:snippet]
from fastapi_validation_override import (
    override_validation_error,
    patch_422_responses,
)

# 1. Registers the runtime handler and patches the app's own root /openapi.json.
override_validation_error(app, status_code=400)

# 2. Re-applies the same patch to each version's own schema.
def versioning_openapi_hook(schema: dict, version: tuple[int, int]) -> dict:
    return patch_422_responses(schema, "400")

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    openapi_hook=versioning_openapi_hook,
).versionize()
# Validation failures now return 400, both at runtime and in every schema
# (root, and every /vX_Y/openapi.json)
# --8<-- [end:snippet]
