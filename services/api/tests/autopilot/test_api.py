from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentshield.container import get_container
from agentshield.deps import reset_services
from agentshield.main import create_app


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("BLOB_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("AUTOPILOT_DEMO_TOKEN", "test-only-token")
    monkeypatch.setenv("NEBIUS_API_KEY", "")
    monkeypatch.setenv("AUTOPILOT_WORKSPACES_DIR", str(tmp_path / "workspaces"))
    get_container.cache_clear()
    reset_services()
    with TestClient(create_app()) as app:
        yield app
    reset_services()
    get_container.cache_clear()


def test_token_protects_fixture_list(client: TestClient) -> None:
    assert client.get("/api/v1/autopilot/fixtures").status_code == 401
    response = client.get(
        "/api/v1/autopilot/fixtures", headers={"Authorization": "Bearer test-only-token"}
    )
    assert response.status_code == 200
    ids = {fixture["fixture_id"] for fixture in response.json()["data"]}
    assert {"buggy-auth", "prompt-injection", "regression-guard"} <= ids


def test_unknown_fixture_is_rejected(client: TestClient) -> None:
    get_container().settings.nebius_api_key = "test-only-key"
    response = client.post(
        "/api/v1/autopilot/jobs",
        headers={"Authorization": "Bearer test-only-token"},
        json={"fixture_id": "not-real", "goal": "Fix tests"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/configuration", None),
        ("POST", "/jobs", {"fixture_id": "buggy-auth", "goal": "Fix auth"}),
        ("GET", "/jobs/unknown", None),
        ("POST", "/jobs/unknown/reset", {}),
    ],
)
def test_missing_key_returns_actionable_error(
    client: TestClient, method: str, path: str, body: dict[str, str] | None
) -> None:
    response = client.request(
        method,
        f"/api/v1/autopilot{path}",
        headers={"Authorization": "Bearer test-only-token"},
        json=body,
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "NEBIUS_API_KEY is not configured. "
        "Set NEBIUS_API_KEY in services/api/.env or export it."
    }


def test_configuration_never_exposes_key(client: TestClient) -> None:
    get_container().settings.nebius_api_key = "test-only-key"
    response = client.get(
        "/api/v1/autopilot/configuration",
        headers={"Authorization": "Bearer test-only-token"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["configured"] is True
    assert "test-only-key" not in response.text


def test_autopilot_openapi_contract(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    prefix = "/api/v1/autopilot"
    for method, path in [
        ("get", "/configuration"),
        ("get", "/fixtures"),
        ("post", "/jobs"),
        ("get", "/jobs/{job_id}"),
        ("get", "/jobs/{job_id}/events"),
        ("get", "/jobs/{job_id}/report"),
        ("post", "/jobs/{job_id}/reset"),
    ]:
        assert method in paths[prefix + path]
    params = paths[prefix + "/jobs/{job_id}/events"]["get"]["parameters"]
    assert any(param["name"] == "since_seq" for param in params)
