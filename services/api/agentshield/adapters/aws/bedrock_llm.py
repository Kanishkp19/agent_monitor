"""Amazon Bedrock implementation of LLMPort, using the Converse API.

`LLMResult` was shaped to mirror this response, so the mapping below is
mechanical -- which is the point. Converse also normalises tool use across
model families, so switching between Haiku and Sonnet is a model-id change.

Throttling is absorbed here with backoff. The domain sees a slow call, never a
`ThrottlingException`; and if Bedrock is genuinely unavailable the adapter
degrades to `MockLLMAdapter` with `fallback=True` rather than stalling the
simulation.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.ports.llm import LLMResult, LLMToolCall, LLMUsage, StopReason

if TYPE_CHECKING:
    from agentshield.config import Settings

logger = logging.getLogger(__name__)

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "stop_sequence": "end_turn",
    "content_filtered": "error",
    "guardrail_intervened": "error",
}

_RETRYABLE = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
        "InternalServerException",
    }
)
_MAX_ATTEMPTS = 3


class BedrockAdapter:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        self._client = (
            client
            if client is not None
            else boto3.client(
                "bedrock-runtime",
                region_name=settings.region,
                config=Config(
                    read_timeout=settings.llm_timeout_seconds, retries={"max_attempts": 0}
                ),
            )
        )
        self._models = {
            "trivial": settings.bedrock_trivial,
            "standard": settings.bedrock_standard,
            "complex": settings.bedrock_complex,
        }
        self._fallback = MockLLMAdapter(seed=settings.sim_seed)
        self._rng = random.Random(settings.sim_seed)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        model_id = self._models.get(model, model)
        kwargs: dict[str, Any] = {
            "modelId": model_id,
            "messages": [
                {"role": m["role"], "content": [{"text": str(m.get("content", ""))}]}
                for m in messages
                if m.get("role") in ("user", "assistant")
            ],
            "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.2},
        }
        # Tools go under toolConfig.tools[].toolSpec -- a flat list here is the
        # single most common source of ValidationException on Converse.
        if tools:
            kwargs["toolConfig"] = {"tools": [{"toolSpec": t} for t in tools]}

        try:
            response = await self._converse_with_backoff(kwargs)
            return _normalise(response, model_id)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            logger.warning(
                "bedrock unavailable, falling back to MockLLM",
                extra={"model": model_id, "code": code},
            )
            result = await self._fallback.complete(
                messages=messages, tools=tools, model=model, max_tokens=max_tokens
            )
            return result.model_copy(update={"fallback": True})

    async def _converse_with_backoff(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        last: ClientError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return dict(await asyncio.to_thread(self._client.converse, **kwargs))
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in _RETRYABLE:
                    raise
                last = exc
                if attempt < _MAX_ATTEMPTS - 1:
                    # Full jitter. Seeded, so a replay of a throttled run is
                    # still reproducible.
                    await asyncio.sleep(self._rng.uniform(0, 2**attempt))
        assert last is not None
        raise last


def _normalise(response: dict[str, Any], model_id: str) -> LLMResult:
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    usage = response.get("usage", {})

    return LLMResult(
        text="".join(b.get("text", "") for b in blocks),
        tool_calls=[
            LLMToolCall(
                id=b["toolUse"]["toolUseId"],
                name=b["toolUse"]["name"],
                arguments=b["toolUse"].get("input") or {},
            )
            for b in blocks
            if "toolUse" in b
        ],
        usage=LLMUsage(
            input_tokens=int(usage.get("inputTokens") or 0),
            output_tokens=int(usage.get("outputTokens") or 0),
        ),
        model_id=model_id,
        stop_reason=_STOP_REASONS.get(str(response.get("stopReason") or ""), "end_turn"),
        fallback=False,
    )
