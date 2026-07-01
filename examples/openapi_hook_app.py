from typing import Any

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version

app = FastAPI(
    title="OpenAPI Hook Demo",
    description="Demonstrates per-version OpenAPI schema customization via openapi_hook.",
)

router = APIRouter()


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


@router.get("/items")
@api_version((1, 0))
def get_items_v1() -> dict[str, object]:
    return {"version": "1.0", "items": ["a", "b"]}


@router.get("/items")
@api_version((2, 0))
def get_items_v2() -> dict[str, object]:
    return {"version": "2.0", "items": ["a", "b", "c"]}


@router.get("/users")
@api_version((1, 0), deprecate_in=(2, 0))
def get_users() -> dict[str, object]:
    return {"users": ["alice", "bob"]}


# POST /items with an invalid "quantity" (e.g. "not-a-number") returns FastAPI's
# default 422 validation error.
@router.post("/items")
@api_version((1, 0))
def create_item(body: CreateItemRequest) -> dict[str, str]:
    return {"name": body.name, "quantity": str(body.quantity)}


def my_openapi_hook(schema: dict[str, Any], version: VersionT) -> dict[str, Any]:
    # Applied to every version: add a company logo to the docs
    schema["info"]["x-logo"] = {"url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"}

    # Version-specific customization
    if version == (1, 0):
        schema["info"]["description"] = (
            schema["info"].get("description") or ""
        ) + "\n\n> **Note:** v1 is in maintenance mode. Migrate to v2 when ready."
    elif version == (2, 0):
        schema["info"]["description"] = (schema["info"].get("description") or "") + "\n\n> **Current stable release.**"

    return schema


versioner = RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    latest_prefix="/latest",
    include_versions_route=True,
    openapi_hook=my_openapi_hook,
)
versioner.versionize()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8004)
