"""The app boots, and says which adapters it booted with.

`/healthz` naming its adapters is what turns "is this really running on AWS?"
from an inference into a fact -- the first thing to check after flipping
`AGENTSHIELD_ENV`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from agentshield.container import get_container
from agentshield.main import create_app


@pytest.fixture
def client(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # A temporary store per test, so a health check never touches the
    # developer's real `.data/` directory.
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "health.db"))  # type: ignore[operator]
    monkeypatch.setenv("BLOB_DIR", str(tmp_path / "blobs"))  # type: ignore[operator]
    get_container.cache_clear()
    with TestClient(create_app()) as c:
        yield c
    get_container.cache_clear()


def test_healthz_reports_ok(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz_names_the_local_adapter_set(client: TestClient) -> None:
    adapters = client.get("/healthz").json()["adapters"]
    assert adapters["docstore"] == "SqliteDocStore"
    assert adapters["blobs"] == "FsBlobStore"
    assert adapters["bus"] == "MemoryBus"
    assert adapters["clock"] == "SimClock"


def test_default_provider_needs_no_model_installed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh clone must run with no Ollama, no Bedrock and no network.

    The provider is pinned to the code default so this assertion stays
    hermetic against developer `.env` drift (the repo may legitimately run
    `hybrid`, which still degrades to MockLLM offline -- that is the hybrid
    adapter's own contract, tested in the LLM contract suite).
    """
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_container.cache_clear()
    with TestClient(create_app()) as pinned:
        body = pinned.get("/healthz").json()
    get_container.cache_clear()
    assert body["llm_provider"] == "mock"
    assert body["adapters"]["llm"] == "MockLLMAdapter"


def test_readyz_requires_a_responsive_docstore(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
