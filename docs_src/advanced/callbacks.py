from fastapi import APIRouter, FastAPI

from fastapi_router_versioning import RouterVersioner, api_version

app = FastAPI()
router = APIRouter()


# --8<-- [start:snippet]
callback_router = APIRouter()

@callback_router.post("{$url}")
def on_event(body: dict) -> None: ...

@router.post("/items", callbacks=callback_router.routes)
@api_version((1, 0))
def create_item() -> dict: ...
# --8<-- [end:snippet]

RouterVersioner(app=app, routers=router).versionize()
