"""Demonstrate overriding the HTTP status code returned for request validation errors.

By default FastAPI returns 422 Unprocessable Entity for validation errors.
``validation_error_code=400`` makes RouterVersioner register an exception handler
and update the OpenAPI schema to reflect the custom code automatically.

Run:
    python examples/validation_error_code_app.py

Then open http://127.0.0.1:8007/v1_0/docs and try ``POST /v1_0/items`` with body
``{"name": "widget", "quantity": "not-a-number"}`` to see the 400 response from
the server (not a Swagger client-side message).
"""

from pydantic import BaseModel

from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


class CreateItemRequest(BaseModel):
    name: str
    quantity: int


app = FastAPI(
    title="Validation Error Code — Automatic Handler",
    description=(
        "Validation errors return **400 Bad Request** instead of 422.\n\n"
        "Try `POST /v1_0/items` with body `{\"name\": \"widget\", \"quantity\": \"not-a-number\"}` "
        "to see the 400 response from the server."
    ),
)

router = APIRouter()


@router.post("/items")
@api_version((1, 0))
def create_item(body: CreateItemRequest) -> dict[str, str]:
    """Create an item. ``name`` must be a string, ``quantity`` must be an integer."""
    return {"name": body.name, "quantity": str(body.quantity)}


RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    # handle_validation_exceptions=True is the default: no extra code needed.
).versionize()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8007)
