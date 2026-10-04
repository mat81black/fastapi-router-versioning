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


# --8<-- [start:snippet]
def my_openapi_hook(schema: dict, version: tuple[int, int]) -> dict:
    schema["info"]["x-logo"] = {"url": "https://example.com/logo.png"}

    if version == (1, 0):
        description = schema["info"].get("description", "")
        schema["info"]["description"] = f"{description}\n\n**DEPRECATED:** Use v2."

    return schema

RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    openapi_hook=my_openapi_hook,
).versionize()
# --8<-- [end:snippet]
