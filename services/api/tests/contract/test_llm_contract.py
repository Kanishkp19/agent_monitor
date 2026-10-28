"""LLMPort contract.

Bedrock is exercised against a stub client rather than moto, which does not
implement `bedrock-runtime.converse`. The stub returns a genuine Converse
response body, so what is under test is the mapping -- which is the only part
of the adapter that can silently differ from Ollama's.

The one property that matters: whatever the provider, the caller receives an
`LLMResult` with the same shape, so `agent/runner.py` has no provider branch.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentshield.adapters.aws.bedrock_llm import BedrockAdapter
from agentshield.adapters.local.hybrid_llm import HybridAdapter
from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.adapters.local.openai_compat_llm import OpenAICompatAdapter
from agentshield.config import Settings
from agentshield.ports.llm import LLMResult, LLMUsage

pytestmark = pytest.mark.contract

_MESSAGES = [{"role": "user", "content": "task_type=bug_fix Fix the payment API error"}]
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


class _StubConverseClient:
    """Returns a real-shaped Converse response, including a toolUse block."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"text": "I'll start by reading the handler."},
                        {
                            "toolUse": {
                                "toolUseId": "tooluse_abc123",
                                "name": "read_file",
                                "input": {
                                    "repo": "payments-api",
                                    "path": "src/handlers/payment.py",
                                },
                            }
                        },
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {"inputTokens": 1204, "outputTokens": 380},
        }


@pytest.fixture(params=["mock", "bedrock"])
def llm(request: pytest.FixtureRequest) -> Any:
    if request.param == "mock":
        return MockLLMAdapter(seed=20260918)
    settings = Settings()
    return BedrockAdapter(settings, client=_StubConverseClient())


async def test_returns_an_llm_result(llm: Any) -> None:
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert isinstance(result, LLMResult)


async def test_usage_is_populated(llm: Any) -> None:
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0


async def test_model_id_is_reported(llm: Any) -> None:
    """Cost is computed from the model actually used, not the one requested."""
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.model_id


async def test_tool_calls_are_normalised(llm: Any) -> None:
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.tool_calls, "both providers should open with a tool call"
    call = result.tool_calls[0]
    assert call.id and call.name
    assert isinstance(call.arguments, dict)


async def test_stop_reason_matches_tool_presence(llm: Any) -> None:
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    expected = "tool_use" if result.tool_calls else "end_turn"
    assert result.stop_reason == expected


async def test_fallback_defaults_to_false_on_success(llm: Any) -> None:
    result = await llm.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    assert result.fallback is False


async def test_bedrock_nests_tools_under_toolspec() -> None:
    """The single most common source of Converse ValidationException.

    Tools go under `toolConfig.tools[].toolSpec`, never as a flat list.
    """
    client = _StubConverseClient()
    adapter = BedrockAdapter(Settings(), client=client)

    await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="complex")

    tool_config = client.calls[0]["toolConfig"]
    assert list(tool_config) == ["tools"]
    assert "toolSpec" in tool_config["tools"][0]


async def test_bedrock_falls_back_rather_than_stalling() -> None:
    """A provider outage degrades the session, it does not halt the simulation.

    The substitution is recorded on the result so no demo ever reports a
    synthetic number as a real one.
    """

    class _Broken:
        def converse(self, **kwargs: Any) -> dict[str, Any]:
            from botocore.exceptions import ClientError

            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "no model access"}},
                "Converse",
            )

    adapter = BedrockAdapter(Settings(), client=_Broken())
    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.fallback is True
    assert isinstance(result, LLMResult)


async def test_mock_is_deterministic() -> None:
    """Same seed, same conversation, byte-identical result.

    Without this the detector cannot be evaluated and the demo cannot be
    rehearsed.
    """
    a = MockLLMAdapter(seed=20260918)
    b = MockLLMAdapter(seed=20260918)

    first = await a.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    second = await b.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert first.model_dump() == second.model_dump()


async def test_mock_advances_through_its_script() -> None:
    """Iteration is derived from the conversation, so replay is exact."""
    adapter = MockLLMAdapter(seed=20260918)
    messages = list(_MESSAGES)
    tools_seen: list[str] = []

    for _ in range(4):
        result = await adapter.complete(messages=messages, tools=_TOOLS, model="standard")
        tools_seen.extend(c.name for c in result.tool_calls)
        messages.append({"role": "assistant", "content": result.text})

    assert tools_seen == ["read_file", "run_tests", "edit_file", "run_tests"]


# ──────────────────────────────────────────────────────────────────────
# OpenAI-compatible free cloud (Groq / Gemini / OpenRouter dialect)
# ──────────────────────────────────────────────────────────────────────


def _cloud_settings() -> Settings:
    """Settings for tests: no retries (no backoff sleeps), fast breaker.

    Constructed from the repo `.env`, so the model ids under test are the ones
    actually configured rather than duplicated literals.
    """
    settings = Settings()
    settings.llm_cloud_api_key = "test-key-123"
    settings.llm_cloud_max_retries = 0
    settings.llm_cloud_breaker_threshold = 2
    return settings


def _openai_body() -> dict[str, Any]:
    """A real-shaped `/chat/completions` response, tool call included.

    Arguments arrive as a JSON *string* -- the shape several providers send --
    so the string-parsing path of the normaliser is what is under test.
    """
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Reading the handler first.",
                    "tool_calls": [
                        {
                            "id": "call_01",
                            "type": "function",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps(
                                    {"repo": "payments-api", "path": "src/handlers/payment.py"}
                                ),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 1204, "completion_tokens": 380},
    }


class _FakeOpenAIResponse:
    """Just what the adapter reads: status_code, headers, text, json()."""

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


class _FakeOpenAIClient:
    """Records requests; returns the canned response (or raises it)."""

    def __init__(self, response: _FakeOpenAIResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def post(
        self, url: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> _FakeOpenAIResponse:
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _StubLocal:
    """A controllable second tier for HybridAdapter tests."""

    def __init__(self, fallback: bool = False) -> None:
        self.fallback = fallback
        self.calls = 0

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text="local tier answered",
            tool_calls=[],
            usage=LLMUsage(input_tokens=1, output_tokens=1),
            model_id="qwen2.5-coder:7b",
            stop_reason="end_turn",
            fallback=self.fallback,
        )


async def test_openai_compat_returns_an_llm_result() -> None:
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    adapter = OpenAICompatAdapter(_cloud_settings(), client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert isinstance(result, LLMResult)


async def test_openai_compat_normalises_tool_calls_and_usage() -> None:
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    adapter = OpenAICompatAdapter(_cloud_settings(), client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments["path"] == "src/handlers/payment.py"
    assert result.usage.input_tokens == 1204
    assert result.usage.output_tokens == 380
    assert result.stop_reason == "tool_use"
    assert result.fallback is False


async def test_openai_compat_translates_tools_and_auth() -> None:
    """Converse-shaped `inputSchema.json` must arrive as OpenAI `parameters`,
    and the key must ride the Authorization header, not the body."""
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    adapter = OpenAICompatAdapter(_cloud_settings(), client=client)

    await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    request = client.calls[0]
    assert request["url"].endswith("/chat/completions")
    assert request["headers"]["Authorization"] == "Bearer test-key-123"
    function = request["json"]["tools"][0]["function"]
    assert function["name"] == "read_file"
    parameters = function["parameters"]
    assert parameters["properties"]["path"]["type"] == "string"
    assert parameters["required"] == ["repo", "path"]


async def test_openai_compat_without_key_runs_scripted() -> None:
    """No key configured is not an error -- it is an honest, recorded
    substitution, so an offline machine still produces a working office."""
    settings = Settings()
    settings.llm_cloud_api_key = ""
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    adapter = OpenAICompatAdapter(settings, client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.fallback is True
    assert client.calls == [], "no request may leave without a key"


async def test_openai_compat_falls_back_after_rate_limits() -> None:
    client = _FakeOpenAIClient(_FakeOpenAIResponse(status_code=429, headers={"retry-after": "0"}))
    adapter = OpenAICompatAdapter(_cloud_settings(), client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.fallback is True
    assert isinstance(result, LLMResult)


async def test_openai_compat_translates_runner_history_for_strict_providers() -> None:
    """The tool loop records history in Ollama-lenient shapes (singular
    `tool_call`, tool results as `role: user` + `tool_call_id`). Strict
    OpenAI-dialect providers reject both with a 400 on the second turn --
    so the adapter, not the domain, does the translation."""
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    adapter = OpenAICompatAdapter(_cloud_settings(), client=client)
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "task_type=bug_fix Fix the payment API error"},
        {
            "role": "assistant",
            "content": "Calling read_file.",
            "tool_call": {"id": "call_01", "name": "read_file", "arguments": {"path": "a.py"}},
        },
        {
            "role": "user",
            "content": '[tool_result:read_file] {"ok":true}',
            "tool_call_id": "call_01",
        },
    ]

    await adapter.complete(messages=messages, tools=_TOOLS, model="standard")

    sent = client.calls[0]["json"]["messages"]
    assert sent[2]["tool_calls"][0]["function"]["name"] == "read_file"
    assert sent[2]["tool_calls"][0]["function"]["arguments"] == '{"path":"a.py"}'
    assert sent[3]["role"] == "tool"
    assert sent[3]["tool_call_id"] == "call_01"


async def test_openai_compat_reports_the_model_actually_used() -> None:
    client = _FakeOpenAIClient(_FakeOpenAIResponse(body=_openai_body()))
    settings = _cloud_settings()
    adapter = OpenAICompatAdapter(settings, client=client)

    result = await adapter.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.model_id == settings.llm_cloud_model_standard


# ──────────────────────────────────────────────────────────────────────
# Hybrid: cloud -> ollama -> mock, with a breaker on the cloud tier
# ──────────────────────────────────────────────────────────────────────


def _hybrid(
    response: _FakeOpenAIResponse | Exception | None, local: _StubLocal | None = None
) -> tuple[HybridAdapter, _FakeOpenAIClient, _StubLocal]:
    settings = _cloud_settings()
    client = _FakeOpenAIClient(response or _FakeOpenAIResponse(body=_openai_body()))
    cloud = OpenAICompatAdapter(settings, client=client)
    local = local or _StubLocal()
    return HybridAdapter(settings, cloud=cloud, local=local), client, local


async def test_hybrid_prefers_the_cloud_tier() -> None:
    hybrid, client, local = _hybrid(None)

    result = await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert len(client.calls) == 1
    assert local.calls == 0
    assert result.model_id.startswith("openai/gpt-oss-")


async def test_hybrid_falls_through_to_local_when_cloud_degrades() -> None:
    """A rate-limited cloud must not cost the session its real model: the
    local tier may still answer, and only then does mock substitution happen."""
    rate_limited = _FakeOpenAIResponse(status_code=429, headers={"retry-after": "0"})
    hybrid, client, local = _hybrid(rate_limited)

    result = await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert len(client.calls) == 1
    assert local.calls == 1
    assert result.fallback is False, "a real local model is not a fallback"
    assert result.text == "local tier answered"


async def test_hybrid_without_key_skips_cloud_entirely() -> None:
    settings = Settings()
    settings.llm_cloud_api_key = ""
    local = _StubLocal()
    hybrid = HybridAdapter(settings, cloud=None, local=local)

    result = await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert local.calls == 1
    assert result.model_id == "qwen2.5-coder:7b"


async def test_hybrid_breaker_skips_cloud_after_repeated_failures() -> None:
    """After the threshold consecutive cloud failures the breaker opens and
    stops paying the timeout on every call -- the next request goes straight
    to the local tier without touching the provider."""
    settings = _cloud_settings()
    settings.llm_cloud_breaker_threshold = 1
    settings.llm_cloud_breaker_cooldown_s = 300
    client = _FakeOpenAIClient(_FakeOpenAIResponse(status_code=429, headers={"retry-after": "0"}))
    cloud = OpenAICompatAdapter(settings, client=client)
    local = _StubLocal()
    hybrid = HybridAdapter(settings, cloud=cloud, local=local)

    await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")
    await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert len(client.calls) == 1, "breaker must stop calls to the failing tier"
    assert local.calls == 2


async def test_hybrid_passes_local_mock_substitution_through_honestly() -> None:
    """When the local tier is Ollama-unreachable and it substituted mock, the
    `fallback` flag must survive -- the demo never claims a real model answered."""
    rate_limited = _FakeOpenAIResponse(status_code=429, headers={"retry-after": "0"})
    hybrid, _client, _local = _hybrid(rate_limited, local=_StubLocal(fallback=True))

    result = await hybrid.complete(messages=_MESSAGES, tools=_TOOLS, model="standard")

    assert result.fallback is True
