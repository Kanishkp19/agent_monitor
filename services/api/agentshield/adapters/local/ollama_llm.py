"""Ollama implementation of LLMPort.

The translation work lives here, not in the domain. Ollama's chat response is
normalised *into* the Bedrock-shaped `LLMResult`, which is the correct
direction: the local adapter adapts, so that moving to Bedrock changes nothing
upstream.

If Ollama is unreachable or slow, this adapter does not raise into the
simulation -- it hands back a `MockLLMAdapter` result with `fallback=True`, and
the event records that the number was synthetic. A demo that stalls on a model
download is worse than a demo that is honest about substituting one.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.ports.llm import LLMResult, LLMToolCall, LLMUsage, StopReason

if TYPE_CHECKING:
    from agentshield.config import Settings

logger = logging.getLogger(__name__)

_STOP_REASONS: dict[str, StopReason] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "load": "error",
}


class OllamaAdapter:
    def __init__(self, settings: Settings) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._timeout = settings.llm_timeout_seconds
        self._models = {
            "trivial": settings.ollama_model_trivial,
            "standard": settings.ollama_model_standard,
            "complex": settings.ollama_model_standard,
        }
        self._fallback = MockLLMAdapter(seed=settings.sim_seed)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        model_id = self._models.get(model, model)
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                return _normalise(response.json(), model_id)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning(
                "ollama unavailable, falling back to MockLLM",
                extra={"model": model_id, "error": str(exc)},
            )
            result = await self._fallback.complete(
                messages=messages, tools=tools, model=model, max_tokens=max_tokens
            )
            return result.model_copy(update={"fallback": True})


def _normalise(raw: dict[str, Any], model_id: str) -> LLMResult:
    """Map Ollama's `/api/chat` response onto `LLMResult`."""
    message = raw.get("message") or {}

    tool_calls = [
        LLMToolCall(
            id=f"call_{index:02d}",
            name=str(call.get("function", {}).get("name", "")),
            arguments=_as_dict(call.get("function", {}).get("arguments")),
        )
        for index, call in enumerate(message.get("tool_calls") or [])
    ]

    return LLMResult(
        text=str(message.get("content") or ""),
        tool_calls=tool_calls,
        usage=LLMUsage(
            input_tokens=int(raw.get("prompt_eval_count") or 0),
            output_tokens=int(raw.get("eval_count") or 0),
        ),
        model_id=model_id,
        stop_reason="tool_use"
        if tool_calls
        else _STOP_REASONS.get(str(raw.get("done_reason") or "stop"), "end_turn"),
        fallback=False,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    """Ollama returns tool arguments as an object; some builds return a JSON
    string. Accept both rather than letting a model quirk fail a session.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
