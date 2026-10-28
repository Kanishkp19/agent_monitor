"""Nebius Token Factory adapter contract (NVIDIA Nemotron).

The wire dialect is OpenAI-compatible, shared with the free-tier adapter --
what is under test here is the part that differs: the **failure contract**.
A qualifying live run must never substitute scripted output, so a missing
key, an exhausted retry budget and a provider rejection all raise typed
errors instead of returning a `fallback=True` result.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.adapters.local.nebius_llm import NebiusAdapter
from agentshield.config import Settings
from agentshield.ports.llm import (
    LLMNotConfigured,
    LLMProviderError,
    LLMResult,
    LLMUnavailable,
)

pytestmark = pytest.mark.contract

_MESSAGES = [{"role": "user", "content": "task_type=bug_fix Fix the auth test"}]
_TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from a repository",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {"repo": {"type": "string"}, "path": {"type": "string"}},
                "required": ["repo", "path"],
            }
        },
    }
]


def _nebius_settings(**overrides: Any) -> Settings:
    settings = Settings()
    settings.nebius_api_key = "test-key-123"
    settings.nebius_max_retries = 0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _nebius_body() -> dict[str, Any]:
    """A real-shaped `/chat/completions` response with a tool call."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "I will read the failing test first.",
                    "tool_calls": [
                        {
                            "id": "call_01",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps(
                                    {"repo": "buggy-auth", "path": "app/auth.py"}
                                ),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 900, "completion_tokens": 120},
    }


class _FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = json.dumps(self._body)

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise ValueError(f"HTTP {self.status_code}")


class _FakeClient:
    def __init__(self, response: _FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _adapter(
    response: _FakeResponse | Exception | None,
    settings: Settings | None = None,
) -> tuple[NebiusAdapter, _FakeClient]:
    client = _FakeClient(response or _FakeResponse(body=_nebius_body()))
    return NebiusAdapter(settings or _nebius_settings(), client=client), client


async def test_returns_an_llm_result() -> None:
    adapter, _ = _adapter(None)
    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert isinstance(result, LLMResult)
    assert result.fallback is False


async def test_reports_the_nemotron_model_id() -> None:
    settings = _nebius_settings()
    adapter, _ = _adapter(None, settings)
    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.model_id == settings.nebius_model
    assert "nemotron" in result.model_id.lower()


async def test_usage_and_tool_calls_are_normalised() -> None:
    adapter, _ = _adapter(None)
    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.usage.input_tokens == 900
    assert result.usage.output_tokens == 120
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments["path"] == "app/auth.py"
    assert result.stop_reason == "tool_use"


async def test_malformed_tool_arguments_fail_explicitly() -> None:
    body = _nebius_body()
    body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{bad"
    adapter, _ = _adapter(_FakeResponse(body=body))
    with pytest.raises(LLMProviderError, match="malformed tool arguments"):
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")


async def test_multi_tool_history_is_translated_for_provider() -> None:
    adapter, client = _adapter(None)
    history = [
        {"role": "user", "content": "Inspect two files"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "one", "name": "read_file", "arguments": {"path": "app/auth.py"}},
            {"id": "two", "name": "read_file", "arguments": {"path": "tests/test_auth.py"}},
        ]},
        {"role": "user", "tool_call_id": "one", "content": "first file"},
        {"role": "user", "tool_call_id": "two", "content": "second file"},
    ]
    await adapter.complete(messages=history, tools=_TOOLS, model="standard")
    wire = client.calls[0]["json"]["messages"]
    assert len(wire[1]["tool_calls"]) == 2
    assert wire[2]["role"] == "tool" and wire[3]["tool_call_id"] == "two"


async def test_translates_tools_and_auth_header() -> None:
    adapter, client = _adapter(None)
    await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    request = client.calls[0]
    assert request["url"].endswith("/chat/completions")
    assert request["headers"]["Authorization"] == "Bearer test-key-123"
    function = request["json"]["tools"][0]["function"]
    assert function["name"] == "read_file"
    assert function["parameters"]["required"] == ["repo", "path"]


# ── the no-substitution failure contract ─────────────────────────────


async def test_missing_key_raises_never_falls_back() -> None:
    """The one behaviour that must never regress: without credentials the
    adapter raises. It does not silently answer with MockLLM."""
    settings = _nebius_settings()
    settings.nebius_api_key = ""
    adapter, client = _adapter(None, settings)

    with pytest.raises(LLMNotConfigured):
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert client.calls == [], "no request may leave without a key"


async def test_auth_failure_raises_provider_error() -> None:
    adapter, client = _adapter(
        _FakeResponse(status_code=401, body={"error": {"message": "bad key"}})
    )

    with pytest.raises(LLMProviderError) as excinfo:
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert excinfo.value.status == 401
    assert client.calls, "the 401 must reach the provider before failing"


async def test_unknown_model_raises_provider_error() -> None:
    adapter, _ = _adapter(
        _FakeResponse(status_code=404, body={"error": {"message": "no such model"}})
    )

    with pytest.raises(LLMProviderError) as excinfo:
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert excinfo.value.status == 404


async def test_rate_limit_exhausting_retries_raises_unavailable() -> None:
    adapter, client = _adapter(_FakeResponse(status_code=429, headers={"retry-after": "0"}))

    with pytest.raises(LLMUnavailable):
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert len(client.calls) == 1, "max_retries=0 means exactly one attempt"


async def test_transport_error_raises_unavailable() -> None:
    adapter, _ = _adapter(httpx.ConnectError("connection reset"))
    with pytest.raises(LLMUnavailable):
        await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")


async def test_result_is_never_mock_scripted() -> None:
    """Even a successful path must prove its text came from the wire, not
    from the seeded mock script (mock answers start with 'Reading '.)."""
    adapter, _ = _adapter(None)
    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    mock = await MockLLMAdapter(seed=20260918).complete(
        messages=_MESSAGES, tools=_TOOLS, model="standard"
    )
    assert result.text != mock.text or result.tool_calls != mock.tool_calls


# ── retry behaviour ──────────────────────────────────────────────────


class _FlakyClient:
    """429 once, then success -- exercises the bounded backoff loop."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if len(self.calls) == 1:
            return _FakeResponse(status_code=429, headers={"retry-after": "0"})
        return _FakeResponse(body=_nebius_body())


async def test_recovers_after_one_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("asyncio.sleep", _noop_sleep)
    client = _FlakyClient()
    settings = _nebius_settings()
    settings.nebius_max_retries = 2
    adapter = NebiusAdapter(settings, client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert len(client.calls) == 2
    assert result.usage.input_tokens == 900


async def _noop_sleep(_seconds: float) -> None:  # pragma: no cover - trivial
    return None
