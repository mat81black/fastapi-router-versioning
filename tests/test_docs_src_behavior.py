import importlib.util

from pathlib import Path
from typing import Any

import pytest

from fastapi.testclient import TestClient

DOCS_SRC = Path(__file__).parent.parent / "docs_src"


def load(name: str) -> Any:
    """Import docs_src/<name>.py, which builds and versionizes the app the page describes."""
    spec = importlib.util.spec_from_file_location(f"docs_src_{name.replace('/', '_')}", DOCS_SRC / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def schema(client: TestClient, prefix: str) -> dict[str, Any]:
    response = client.get(f"{prefix}/openapi.json")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_quickstart_semver_mounts_each_version_with_its_own_docs() -> None:
    client = TestClient(load("quickstart/semver").app)

    assert client.get("/v1_0/items").json() == {"version": "1.0", "items": ["a", "b"]}
    assert client.get("/v2_0/items").json() == {"version": "2.0", "items": ["a", "b", "c"]}
    for prefix in ("/v1_0", "/v2_0"):
        assert client.get(f"{prefix}/docs").status_code == 200
        assert client.get(f"{prefix}/redoc").status_code == 200
        assert list(schema(client, prefix)["paths"]) == [f"{prefix}/items"]


def test_quickstart_calver_mounts_the_date_prefix() -> None:
    client = TestClient(load("quickstart/calver").app)

    assert client.get("/2025-01-01/items").json() == {"release": "2025-01-01"}
    assert client.get("/2025-01-01/docs").status_code == 200
    assert list(schema(client, "/2025-01-01")["paths"]) == ["/2025-01-01/items"]


def test_lifecycle_route_is_deprecated_then_removed() -> None:
    client = TestClient(load("lifecycle/legacy_route").app)

    assert "deprecated" not in schema(client, "/v1_0")["paths"]["/v1_0/legacy"]["get"]
    assert schema(client, "/v2_0")["paths"]["/v2_0/legacy"]["get"]["deprecated"] is True
    assert client.get("/v2_0/legacy").status_code == 200  # deprecated routes are still served
    assert schema(client, "/v3_0")["paths"] == {}
    assert client.get("/v3_0/legacy").status_code == 404


def test_latest_alias_points_at_the_highest_version() -> None:
    client = TestClient(load("advanced/latest_alias").app)

    assert client.get("/latest/items").json() == client.get("/v2_0/items").json()
    assert schema(client, "/latest")["info"]["version"] == "2.0"


def test_custom_url_format_changes_prefixes_and_titles() -> None:
    client = TestClient(load("advanced/custom_url_format").app)

    for prefix in ("/v1", "/v2", "/latest"):
        assert client.get(f"{prefix}/items").status_code == 200
    assert client.get("/v1_0/items").status_code == 404
    assert schema(client, "/v1")["info"]["title"] == "FastAPI - v1"
    assert schema(client, "/v2")["info"]["title"] == "FastAPI - v2"


def test_version_discovery_endpoint_lists_every_version() -> None:
    client = TestClient(load("advanced/version_discovery").app)

    assert client.get("/versions").json() == {
        "versions": [
            {
                "version": "1.0",
                "openapi_url": "/v1_0/openapi.json",
                "swagger_url": "/v1_0/docs",
                "redoc_url": "/v1_0/redoc",
            },
            {
                "version": "2.0",
                "openapi_url": "/v2_0/openapi.json",
                "swagger_url": "/v2_0/docs",
                "redoc_url": "/v2_0/redoc",
            },
        ]
    }


def test_deprecation_headers_come_from_version_info() -> None:
    client = TestClient(load("advanced/deprecation_headers").app)

    not_deprecated = client.get("/v1_0/legacy")
    assert not any(name in not_deprecated.headers for name in ("deprecation", "sunset", "link"))

    deprecated = client.get("/v2_0/legacy")
    assert deprecated.headers["deprecation"] == "@1740787200"  # 2025-03-01T00:00:00Z, v2.0's release_date
    assert deprecated.headers["sunset"] == "Thu, 01 Jan 2026 00:00:00 GMT"  # v3.0's release_date, where it is removed
    assert deprecated.headers["link"] == '<https://api.example.com/docs/upgrade/v2>; rel="deprecation"'


def test_openapi_hook_edits_each_version_schema() -> None:
    client = TestClient(load("advanced/openapi_hook").app)

    first = schema(client, "/v1_0")["info"]
    second = schema(client, "/v2_0")["info"]
    assert first["x-logo"] == second["x-logo"] == {"url": "https://example.com/logo.png"}
    assert "**DEPRECATED:** Use v2." in first["description"]
    assert "description" not in second


def test_callback_hook_runs_for_every_version(capsys: pytest.CaptureFixture[str]) -> None:
    load("advanced/callback_hook")

    output = capsys.readouterr().out
    assert "Registered version (1, 0) at /v1_0" in output
    assert "Registered version (2, 0) at /v2_0" in output


def test_multiple_routers_share_the_version_prefix() -> None:
    client = TestClient(load("advanced/multiple_routers").app)

    assert client.get("/v1_0/users").status_code == 200
    assert client.get("/v1_0/products").status_code == 200


def test_self_hosted_assets_replace_the_cdn_urls() -> None:
    client = TestClient(load("advanced/self_hosted_assets").app)

    swagger = client.get("/v1_0/docs").text
    for asset in ("/static/swagger-ui-bundle.js", "/static/swagger-ui.css", "/static/favicon.png"):
        assert asset in swagger
    redoc = client.get("/v1_0/redoc").text
    assert "/static/redoc.standalone.js" in redoc
    assert "/static/favicon.png" in redoc
    assert "fonts.googleapis.com" not in redoc


def test_mounted_app_docs_point_at_the_mount_path() -> None:
    client = TestClient(load("advanced/reverse_proxy").parent)

    assert "/api/v1_0/openapi.json" in client.get("/api/v1_0/docs").text


def test_validation_status_code_applies_at_runtime_and_in_every_schema() -> None:
    client = TestClient(load("advanced/validation_error_status_code").app)

    assert client.get("/v1_0/items/not-a-number").status_code == 400
    for prefix in ("", "/v1_0"):  # the app's own schema, and the one of a version
        responses = schema(client, prefix)["paths"]["/v1_0/items/{item_id}"]["get"]["responses"]
        assert "400" in responses
        assert "422" not in responses


def test_webhooks_follow_the_route_lifecycle() -> None:
    client = TestClient(load("advanced/webhooks").app)

    def payload(version: str) -> str:
        post = schema(client, version)["webhooks"]["/order-created"]["post"]
        return str(post["requestBody"]["content"]["application/json"]["schema"]["$ref"])

    assert set(schema(client, "/v1_0")["webhooks"]) == {"/order-created", "/payment-failed"}
    assert set(schema(client, "/v2_0")["webhooks"]) == {"/order-created"}
    assert payload("/v1_0").endswith("OrderV1")
    assert payload("/v2_0").endswith("OrderV2")


def test_route_callbacks_are_carried_into_the_version() -> None:
    client = TestClient(load("advanced/callbacks").app)

    assert schema(client, "/v1_0")["paths"]["/v1_0/items"]["post"]["callbacks"]
