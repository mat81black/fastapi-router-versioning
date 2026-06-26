"""Demonstrate using a custom validation exception handler alongside validation_error_code.

Setting ``handle_validation_exceptions=False`` tells RouterVersioner to update the
OpenAPI schema (so it shows 400 instead of 422) without registering any handler.
You then register your own handler for full control over the response body.

Run:
    python examples/validation_error_code_custom_handler_app.py

Then open http://127.0.0.1:8008/v1_0/docs and try ``POST /v1_0/orders`` with body
``{"name": "widget", "quantity": "not-a-number"}`` to see the custom 400 response
with field-level error messages.
"""

from pydantic import BaseModel

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version


class CreateOrderRequest(BaseModel):
    name: str
    quantity: int


app = FastAPI(
    title="Validation Error Code — Custom Handler",
    description=(
        "Validation errors return **400 Bad Request** with a custom response body.\n\n"
        "Try `POST /v1_0/orders` with body `{\"name\": \"widget\", \"quantity\": \"not-a-number\"}` "
        "to see the custom handler response."
    ),
)

router = APIRouter()


@router.post("/orders")
@api_version((1, 0))
def create_order(body: CreateOrderRequest) -> dict[str, str]:
    """Create an order. ``name`` must be a string, ``quantity`` must be an integer."""
    return {"name": body.name, "quantity": str(body.quantity)}


@app.exception_handler(RequestValidationError)
async def my_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Returns field-level error messages under an 'errors' key."""
    return JSONResponse(
        status_code=400,
        content={
            "errors": [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()],
        },
    )


RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    handle_validation_exceptions=False,  # OpenAPI schema shows 400; handler is yours.
).versionize()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8008)
