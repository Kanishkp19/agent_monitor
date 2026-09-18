"""LLMPort contract.

Bedrock is exercised against a stub client rather than moto, which does not
implement `bedrock-runtime.converse`. The stub returns a genuine Converse
response body, so what is under test is the mapping -- which is the only part
of the adapter that can silently differ from Ollama's.

The one property that matters: whatever the provider, the caller receives an
`LLMResult` with the same shape, so `agent/runner.py` has no provider branch.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentshield.adapters.aws.bedrock_llm import BedrockAdapter
from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.config import Settings
from agentshield.ports.llm import LLMResult

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
