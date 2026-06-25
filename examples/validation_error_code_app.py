"""Demonstrate overriding the HTTP status code returned for request validation errors.

By default FastAPI returns 422 Unprocessable Entity for validation errors.
RouterVersioner lets you change this to any code (e.g. 400 Bad Request) via
``validation_error_code``.

Two approaches are shown:

1. Let RouterVersioner register the exception handler automatically
   (``handle_validation_exceptions=True``, the default).
2. Register your own handler for full control over the response body
   (``handle_validation_exceptions=False``).
"""

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from fastapi_router_versioning import RouterVersioner, VersionFormat, api_version

# ── Approach 1: automatic handler ────────────────────────────────────────────
app = FastAPI(
    title="Validation Error Code Override",
    description="Shows how to return 400 instead of 422 for validation errors.",
)

router = APIRouter()


@router.get("/items")
@api_version((1, 0))
def get_items(count: int) -> dict[str, str]:
    """Returns a list of items. ``count`` must be a valid integer."""
    return {"count": str(count)}


RouterVersioner(
    app=app,
    routers=router,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    # handle_validation_exceptions=True is the default: RouterVersioner registers
    # the handler automatically, so no extra code is needed here.
).versionize()


# ── Approach 2: custom handler ────────────────────────────────────────────────
app2 = FastAPI(
    title="Custom Validation Handler",
    description="Shows handle_validation_exceptions=False with a user-defined handler.",
)

router2 = APIRouter()


@router2.get("/orders")
@api_version((1, 0))
def get_orders(count: int) -> dict[str, str]:
    return {"count": str(count)}


@app2.exception_handler(RequestValidationError)
async def my_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"errors": [e["msg"] for e in exc.errors()], "path": str(request.url)},
    )


RouterVersioner(
    app=app2,
    routers=router2,
    version_format=VersionFormat.SEMVER,
    validation_error_code=400,
    handle_validation_exceptions=False,  # Schema says 400; handler is yours.
).versionize()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
