from enum import Enum
from typing import Any

import pytest

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fastapi_router_versioning import RouterVersioner, VersionFormat, VersionT, api_version


def test_docs_and_latest_prefix() -> None:
    """Swagger, ReDoc, OpenAPI JSON, and the latest_prefix alias are all reachable."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/docs-test")
    @api_version((1, 0))
    def docs_route() -> dict[str, str]:
        return {"msg": "ok"}

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/vlatest")
    versioner.versionize()

    client = TestClient(app)

    assert client.get("/v1_0/openapi.json").status_code == 200
    assert client.get("/v1_0/docs").status_code == 200
    assert client.get("/v1_0/redoc").status_code == 200

    assert client.get("/vlatest/docs-test").status_code == 200
    assert client.get("/vlatest/openapi.json").status_code == 200


def test_openapi_with_root_path_and_oauth2() -> None:
    """OpenAPI JSON includes a server entry when the app is mounted behind a proxy (root_path)."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/docs/oauth2-redirect").status_code == 200

    # Simulate a reverse-proxy setup by passing root_path to the test client.
    client_proxy = TestClient(app, root_path="/api")
    response = client_proxy.get("/v1_0/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert "servers" in schema
    assert schema["servers"][0]["url"] == "/api"


def test_openapi_tags_filtering_coverage() -> None:
    """Only tags actually used by routes in a given version appear in that version's OpenAPI schema."""
    app_tags = [
        {"name": "auth", "description": "Authentication"},
        {"name": "users", "description": "User management (not used in v1)"},
    ]
    app = FastAPI(openapi_tags=app_tags)
    router = APIRouter()

    @router.get("/login", tags=["auth"])
    @api_version((1, 0))
    def login_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "tags" in schema

    assert len(schema["tags"]) == 1
    assert schema["tags"][0]["name"] == "auth"


def test_openapi_tags_filtering_matches_enum_tags() -> None:
    """FastAPI's own "Tags with Enums" tutorial recommends tags=[Tags.items] where Tags is a
    plain Enum (not str, Enum): those members aren't equal to their own string value, so tag
    filtering must normalize them before comparing against openapi_tags[i]["name"].
    """

    class Tags(Enum):
        items = "items"
        users = "users"

    app_tags = [
        {"name": "items", "description": "Manage items"},
        {"name": "users", "description": "User management (not used here)"},
    ]
    app = FastAPI(openapi_tags=app_tags)
    router = APIRouter()

    @router.get("/items", tags=[Tags.items])
    @api_version((1, 0))
    def get_items() -> list[str]: ...

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()

    client = TestClient(app)
    schema = client.get("/v1_0/openapi.json").json()

    assert schema["tags"] == [{"name": "items", "description": "Manage items"}]


def test_openapi_hook_is_applied_to_schema() -> None:
    """openapi_hook receives the generated schema and the current version; its return value is served."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    @router.get("/test")
    @api_version((2, 0))
    def test_route_v2() -> dict[str, str]: ...

    def my_hook(schema: dict[str, Any], version: tuple[int, int]) -> dict[str, Any]:
        schema["info"]["x-custom"] = f"v{version[0]}.{version[1]}"
        return schema

    versioner = RouterVersioner(
        app=app,
        routers=router,
        version_format=VersionFormat.SEMVER,
        openapi_hook=my_hook,
    )
    versioner.versionize()

    client = TestClient(app)

    response_v1 = client.get("/v1_0/openapi.json")
    assert response_v1.status_code == 200
    assert response_v1.json()["info"]["x-custom"] == "v1.0"

    response_v2 = client.get("/v2_0/openapi.json")
    assert response_v2.status_code == 200
    assert response_v2.json()["info"]["x-custom"] == "v2.0"


def test_openapi_hook_none_does_not_affect_schema() -> None:
    """When openapi_hook is None (default), the schema is returned unmodified."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    assert "x-custom" not in response.json().get("info", {})


def test_failing_openapi_hook_does_not_affect_versionize_or_the_api_route() -> None:
    """A failing openapi_hook is unrelated to versionize()'s fatal-failure contract: the hook
    only runs lazily, when /openapi.json is actually requested, not during versionize()
    itself. versionize() must succeed, the regular API route must keep working, and the
    error must surface only when the schema is fetched.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/item")
    @api_version((1, 0))
    def item() -> dict[str, str]:
        return {"ok": "true"}

    def failing_openapi_hook(_schema: dict[str, Any], _version: VersionT) -> dict[str, Any]:
        raise RuntimeError("OpenAPI generation failed")

    versioner = RouterVersioner(
        app=app, routers=router, version_format=VersionFormat.SEMVER, openapi_hook=failing_openapi_hook
    )
    versions = versioner.versionize()
    assert versions == [(1, 0)]

    client = TestClient(app)
    assert client.get("/v1_0/item").json() == {"ok": "true"}

    with pytest.raises(RuntimeError, match="OpenAPI generation failed"):
        client.get("/v1_0/openapi.json")


def test_openapi_tags_empty_when_no_route_uses_a_tag() -> None:
    """Tags list is empty when none of the routes in the version carry any tag."""
    app = FastAPI(openapi_tags=[{"name": "auth", "description": "Authentication"}])
    router = APIRouter()

    @router.get("/ping")
    @api_version((1, 0))
    def ping() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    assert response.json().get("tags") is None


def test_oauth2_redirect_url_is_versioned_in_swagger_html() -> None:
    """The OAuth2 redirect URL embedded in the versioned Swagger HTML points to the versioned path."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    html = client.get("/v1_0/docs").text
    assert "/v1_0/docs/oauth2-redirect" in html


def test_init_oauth_config_propagated_to_versioned_docs() -> None:
    """swagger_ui_init_oauth set on the FastAPI app appears in the versioned Swagger UI HTML."""
    app = FastAPI(swagger_ui_init_oauth={"clientId": "my-app-client", "scopes": "read:api"})
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    html = client.get("/v1_0/docs").text
    assert "my-app-client" in html
    assert "read:api" in html


def test_custom_oauth2_redirect_url_is_versioned() -> None:
    """A custom swagger_ui_oauth2_redirect_url is versioned: both the endpoint and the HTML link."""
    app = FastAPI(swagger_ui_oauth2_redirect_url="/my-oauth2-redirect")
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/my-oauth2-redirect").status_code == 200
    html = client.get("/v1_0/docs").text
    assert "/v1_0/my-oauth2-redirect" in html


def test_oauth2_redirect_disabled_when_no_redirect_url() -> None:
    """When swagger_ui_oauth2_redirect_url=None, no redirect endpoint is registered and
    no oauth2RedirectUrl property appears in the Swagger HTML."""
    app = FastAPI(swagger_ui_oauth2_redirect_url=None)
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/docs/oauth2-redirect").status_code == 404
    html = client.get("/v1_0/docs").text
    assert "oauth2RedirectUrl" not in html


def test_custom_swagger_asset_urls() -> None:
    """Custom JS/CSS/favicon URLs are reflected in the versioned Swagger UI HTML."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        swagger_js_url="https://internal.company.com/swagger-ui-bundle.js",
        swagger_css_url="https://internal.company.com/swagger-ui.css",
        swagger_favicon_url="https://internal.company.com/favicon.ico",
    )
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/docs")
    assert response.status_code == 200
    html = response.text
    assert "https://internal.company.com/swagger-ui-bundle.js" in html
    assert "https://internal.company.com/swagger-ui.css" in html
    assert "https://internal.company.com/favicon.ico" in html


def test_custom_redoc_asset_urls_and_no_google_fonts() -> None:
    """Custom ReDoc JS/favicon URLs and redoc_with_google_fonts=False are reflected in the versioned ReDoc HTML."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        redoc_js_url="https://internal.company.com/redoc.standalone.js",
        redoc_favicon_url="https://internal.company.com/favicon.ico",
        redoc_with_google_fonts=False,
    )
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/redoc")
    assert response.status_code == 200
    html = response.text
    assert "https://internal.company.com/redoc.standalone.js" in html
    assert "https://internal.company.com/favicon.ico" in html
    assert "fonts.googleapis.com" not in html


def test_default_asset_urls_use_cdn() -> None:
    """Without custom asset URLs, versioned docs fall back to FastAPI's default CDN URLs."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    client = TestClient(app)

    swagger_html = client.get("/v1_0/docs").text
    assert "cdn.jsdelivr.net" in swagger_html

    redoc_html = client.get("/v1_0/redoc").text
    assert "cdn.jsdelivr.net" in redoc_html


def test_swagger_and_redoc_openapi_url_includes_root_path_at_request_time() -> None:
    """When the app is behind a reverse proxy, the root_path is injected at request time,
    so the openapi_url in the Swagger/ReDoc HTML reflects the proxy prefix."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router)
    versioner.versionize()

    # Simulate mounting behind a reverse proxy that sets root_path="/prefix"
    client = TestClient(app, root_path="/prefix")

    swagger_html = client.get("/v1_0/docs").text
    assert "/prefix/v1_0/openapi.json" in swagger_html
    assert swagger_html.count("/v1_0/openapi.json") == swagger_html.count("/prefix/v1_0/openapi.json")

    redoc_html = client.get("/v1_0/redoc").text
    assert "/prefix/v1_0/openapi.json" in redoc_html


def test_include_version_docs_false_disables_swagger_and_redoc() -> None:
    """include_version_docs=False: /docs and /redoc return 404; /openapi.json still works."""
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, include_version_docs=False, include_version_openapi_route=True)
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/openapi.json").status_code == 200
    assert client.get("/v1_0/docs").status_code == 404
    assert client.get("/v1_0/redoc").status_code == 404


def test_include_version_openapi_route_false_disables_openapi_json() -> None:
    """include_version_openapi_route=False: /openapi.json returns 404. /docs and /redoc must
    also be disabled, since both fetch their schema from that same, now-missing URL; leaving
    them mounted would only produce a docs page stuck on a fetch error.
    """
    app = FastAPI()
    router = APIRouter()

    @router.get("/test")
    @api_version((1, 0))
    def test_route() -> dict[str, str]: ...

    versioner = RouterVersioner(
        app=app,
        routers=router,
        include_version_docs=True,
        include_version_openapi_route=False,
        include_versions_route=True,
    )
    versioner.versionize()

    client = TestClient(app)
    assert client.get("/v1_0/openapi.json").status_code == 404
    assert client.get("/v1_0/docs").status_code == 404
    assert client.get("/v1_0/redoc").status_code == 404

    version_model = client.get("/versions").json()["versions"][0]
    assert "openapi_url" not in version_model
    assert "swagger_url" not in version_model
    assert "redoc_url" not in version_model


def test_latest_prefix_openapi_schema_is_cached_independently_of_canonical() -> None:
    """The canonical version and its /latest alias share the same `version` value but are
    built from two distinct routers with different prefixes: their OpenAPI schemas must not
    collide in the cache, regardless of which one is requested first.
    """

    def build_app() -> FastAPI:
        app = FastAPI()
        router = APIRouter()

        @router.get("/item")
        @api_version((1, 0))
        def item() -> dict[str, bool]:
            return {"ok": True}

        RouterVersioner(
            app=app, routers=router, version_format=VersionFormat.SEMVER, latest_prefix="/latest"
        ).versionize()
        return app

    # Canonical requested first.
    client_a = TestClient(build_app())
    assert client_a.get("/v1_0/item").json() == {"ok": True}
    schema_v1_a = client_a.get("/v1_0/openapi.json").json()
    schema_latest_a = client_a.get("/latest/openapi.json").json()
    assert list(schema_v1_a["paths"].keys()) == ["/v1_0/item"]
    assert list(schema_latest_a["paths"].keys()) == ["/latest/item"]

    # Alias requested first: the order must not change the outcome.
    client_b = TestClient(build_app())
    assert client_b.get("/latest/item").json() == {"ok": True}
    schema_latest_b = client_b.get("/latest/openapi.json").json()
    schema_v1_b = client_b.get("/v1_0/openapi.json").json()
    assert list(schema_latest_b["paths"].keys()) == ["/latest/item"]
    assert list(schema_v1_b["paths"].keys()) == ["/v1_0/item"]


def test_openapi_callbacks_are_propagated_to_versioned_routes() -> None:
    """OpenAPI callbacks defined on a route are propagated to every versioned copy of that route."""
    app = FastAPI()
    callback_router = APIRouter()

    @callback_router.post("{$url}")
    def on_item_created(body: dict[str, str]) -> None: ...

    router = APIRouter()

    @router.post("/items", callbacks=callback_router.routes)
    @api_version((1, 0))
    def create_item() -> dict[str, str]: ...

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER)
    versioner.versionize()

    client = TestClient(app)
    response = client.get("/v1_0/openapi.json")
    assert response.status_code == 200
    schema = response.json()

    post_op = schema["paths"]["/v1_0/items"]["post"]
    assert "callbacks" in post_op
    assert len(post_op["callbacks"]) > 0


def test_openapi_schema_is_cached() -> None:
    """The schema is generated only once; subsequent requests use the cache."""
    from unittest.mock import patch

    import fastapi.openapi.utils as openapi_utils

    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0))
    def get_data() -> dict[str, str]: ...

    RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER).versionize()
    client = TestClient(app)

    with patch.object(openapi_utils, "get_openapi", wraps=openapi_utils.get_openapi) as mock_fn:
        client.get("/v1_0/openapi.json")
        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 1


def test_openapi_cache_invalidated_on_route_change() -> None:
    """The cache is invalidated when _get_routes_version() changes after a new route is added."""
    from unittest.mock import patch

    import fastapi.openapi.utils as openapi_utils

    import fastapi_router_versioning.versioner as versioner_mod

    if versioner_mod._route_contexts_fn is None:
        pytest.skip("_get_routes_version not available (FastAPI < 0.137.2)")  # pragma: no cover

    app = FastAPI()
    router = APIRouter()

    @router.get("/data")
    @api_version((1, 0))
    def get_data() -> dict[str, str]: ...

    captured_routers: dict[Any, APIRouter] = {}

    def capture_callback(versioned_router: APIRouter, version: VersionT, prefix: str) -> None:
        captured_routers[version] = versioned_router

    versioner = RouterVersioner(app=app, routers=router, version_format=VersionFormat.SEMVER, callback=capture_callback)
    versioner.versionize()
    client = TestClient(app)

    with patch.object(openapi_utils, "get_openapi", wraps=openapi_utils.get_openapi) as mock_fn:
        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 1

        captured_routers[(1, 0)].add_api_route("/dynamic", lambda: {}, methods=["GET"])

        client.get("/v1_0/openapi.json")
        assert mock_fn.call_count == 2
