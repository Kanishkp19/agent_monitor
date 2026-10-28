"""OpenAI-compatible cloud implementation of LLMPort.

One adapter covers every free-tier provider that speaks the OpenAI
`/chat/completions` dialect: Groq (the default), Google Gemini's
OpenAI-compatibility endpoint, OpenRouter, and any self-hosted vLLM or
llama.cpp server. They differ in base URL, key and model ids -- nothing else --
so the translation below is written once.

The same constraints as the sibling adapters:

**Pure translation.** The response is normalised into the Bedrock-shaped
`LLMResult`, so `agent/runner.py` never learns that a third provider dialect
exists.

**Degrade, never stall.** Rate limits, outages and schema quirks fall back to
`MockLLMAdapter` with `fallback=True`. The substitution is recorded on the
`model.invoked` event, so a demo never reports a synthetic number as a real
one. A missing API key short-circuits to the same path -- the honest answer to
"no cloud configured" is "these sessions ran scripted".

**Injectable transport and clock.** The httpx client and the rate limiter can
both be supplied, which is how the contract suite exercises the full mapping
with no network and no wall-clock waiting. The one wall-clock read in here --
the rate limiter -- is legitimate: a provider quota is charged in wall time,
not simulated time, and this adapter is only ever used for live sessions
(`advance()` forces MockLLM regardless of configuration).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.ports.llm import LLMResult, LLMToolCall, LLMUsage, StopReason

if TYPE_CHECKING:
    from agentshield.config import Settings

logger = logging.getLogger(__name__)

_FINISH_REASONS: dict[str, StopReason] = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "content_filter": "end_turn",
}


class RateLimiter:
    """Spaces calls at least `60 / rpm` seconds apart.

    Capacity-one token bucket refilled at `rpm` per minute. Slots are booked
    under the lock and the wait happens outside it, so concurrent sessions
    queue fairly instead of serialising on the lock itself.
    """

    def __init__(self, rpm: int) -> None:
        self._min_interval = 60.0 / max(1, rpm)
        self._next_ok = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Reserve the next slot; return how long the caller must wait."""
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_ok - now)
            self._next_ok = max(now, self._next_ok) + self._min_interval
        if wait > 0:
            await asyncio.sleep(wait)
        return wait


class _RateLimited(Exception):
    """A 429 from the provider, carrying the Retry-After hint if sent."""

    def __init__(self, retry_after: str, body: str) -> None:
        super().__init__(f"rate limited (retry-after={retry_after!r}): {body[:200]}")
        self.retry_after_raw = retry_after


class _ProviderError(Exception):
    """A non-429 provider error, parsed for its structured diagnostics."""

    def __init__(self, status: int, body_text: str) -> None:
        super().__init__(f"HTTP {status}: {body_text[:300]}")
        self.status = status
        self.body_text = body_text
        self.code = ""
        self.failed_generation = ""
        try:
            error = (json.loads(body_text) or {}).get("error") or {}
            self.code = str(error.get("code") or "")
            self.failed_generation = str(error.get("failed_generation") or "")
        except json.JSONDecodeError:
            pass


class OpenAICompatAdapter:
    """`/chat/completions` against any OpenAI-compatible free tier."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._base_url = settings.llm_cloud_base_url.rstrip("/")
        self._api_key = settings.llm_cloud_api_key
        self._timeout = settings.llm_timeout_seconds
        self._retries = settings.llm_cloud_max_retries
        self._models = {
            "trivial": settings.llm_cloud_model_trivial,
            "standard": settings.llm_cloud_model_standard,
            "complex": settings.llm_cloud_model_complex,
        }
        self._fallback = MockLLMAdapter(seed=settings.sim_seed)
        self._client = client
        self._limiter = limiter or RateLimiter(settings.llm_cloud_rpm)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        if not self._api_key:
            logger.warning(
                "no cloud API key configured; session runs scripted",
                extra={"model": model},
            )
            result = await self._fallback.complete(
                messages=messages, tools=tools, model=model, max_tokens=max_tokens
            )
            return result.model_copy(update={"fallback": True})

        model_id = self._models.get(model, model)
        payload = _payload(messages, tools, model_id, max_tokens)

        last_error = ""
        correction_used = False
        for attempt in range(self._retries + 1):
            try:
                await self._limiter.acquire()
                raw = await self._post(payload)
                return _normalise(raw, model_id)
            except _RateLimited as exc:
                last_error = str(exc)
                # A provider hint (Retry-After) beats exponential backoff: free
                # tiers replenish tokens-per-minute on a schedule, and waiting
                # exactly that long salvages the call instead of burning a
                # retry cycle into the same full bucket.
                hinted = min(_hinted_seconds(exc), 20.0)
                pause = max(hinted, 0.5 * (2**attempt))
                logger.warning(
                    "cloud llm rate limited; backing off %.1fs",
                    pause,
                    extra={"model": model_id, "attempt": attempt + 1},
                )
                await asyncio.sleep(pause)
            except _ProviderError as exc:
                last_error = str(exc)
                hallucinated = (
                    _parse_failed_generation(exc.failed_generation)
                    if exc.code == "tool_use_failed" and not correction_used
                    else None
                )
                if hallucinated is not None:
                    # gpt-oss models occasionally emit a tool call for a tool
                    # they imagine (e.g. `search_file`). Strict providers
                    # reject the entire request before the runner's own
                    # unknown-tool path can engage -- so the adapter performs
                    # the same correction round-trip here: record the
                    # hallucinated call, answer it with an error naming the
                    # real tools, and re-ask once.
                    correction_used = True
                    tool_names = ", ".join(str(t.get("name", "")) for t in tools)
                    messages = [
                        *messages,
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_call": {
                                "id": "call_unknown_tool",
                                "name": str(hallucinated["name"]),
                                "arguments": hallucinated.get("arguments") or {},
                            },
                        },
                        {
                            "role": "user",
                            "content": f"[tool_result:{hallucinated['name']}] "
                            + json.dumps(
                                {
                                    "error": "unknown_tool",
                                    "message": (
                                        f"tool '{hallucinated['name']}' does not exist. "
                                        f"Available tools: {tool_names}"
                                    ),
                                },
                                separators=(",", ":"),
                            ),
                            "tool_call_id": "call_unknown_tool",
                        },
                    ]
                    logger.warning(
                        "provider rejected hallucinated tool %r; correcting once",
                        str(hallucinated["name"]),
                        extra={"model": model_id},
                    )
                    continue
                logger.warning(
                    "cloud llm call failed: %s",
                    last_error[:300],
                    extra={"model": model_id, "attempt": attempt + 1},
                )
                await asyncio.sleep(0.5 * (2**attempt))
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_error = repr(exc)
                # The exception text rides the message, not `extra`: the
                # default log formatter drops extra fields, and "cloud llm
                # call failed" with no reason is undiagnosable in production.
                logger.warning(
                    "cloud llm call failed: %s",
                    last_error[:300],
                    extra={"model": model_id, "attempt": attempt + 1},
                )
                await asyncio.sleep(0.5 * (2**attempt))

        logger.warning(
            "cloud llm unavailable; session falls back to MockLLM",
            extra={"model": model_id, "error": last_error},
        )
        result = await self._fallback.complete(
            messages=messages, tools=tools, model=model, max_tokens=max_tokens
        )
        return result.model_copy(update={"fallback": True})

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._client is not None:
            response = await self._client.post(
                f"{self._base_url}/chat/completions", json=payload, headers=headers
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        if response.status_code == 429:
            raise _RateLimited(
                str(response.headers.get("retry-after", "")),
                response.text if isinstance(response.text, str) else "",
            )
        if response.status_code >= 400:
            # Provider diagnostics name the exact offending field; swallowing
            # them into a generic HTTPStatusError makes 400s undebuggable.
            body = response.text if isinstance(response.text, str) else ""
            raise _ProviderError(response.status_code, body)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


def _payload(
    messages: list[dict[str, Any]], tools: list[dict[str, Any]], model_id: str, max_tokens: int
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": _normalise_messages(messages),
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if "gpt-oss" in model_id:
        # Reasoning models spend `max_tokens` on hidden thinking; at the default
        # effort a tool-loop call can return empty text with stop_reason
        # max_tokens -- a wasted billed call. Low keeps the office responsive.
        payload["reasoning_effort"] = "low"
    if tools:
        # `agent/tools.py` stores schemas in Bedrock Converse shape
        # (`inputSchema.json`); the OpenAI dialect wants `parameters`.
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": (tool.get("inputSchema") or {}).get("json", {}),
                },
            }
            for tool in tools
        ]
    return payload


def _normalise_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Translate the runner's provider-neutral history into strict OpenAI shape.

    The tool-use loop records history in shapes Ollama accepts as-is:
    assistant turns carry a singular `tool_call` object and tool results ride
    `role: "user"` with a `tool_call_id`. Groq's strict validation rejects
    both with a 400 on the second turn of every session. Bedrock's adapter
    does the same kind of translation into Converse; this is the OpenAI
    dialect's turn, so the domain never learns a provider exists.
    """
    import json as _json

    normalised: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role", ""))
        if role == "assistant" and isinstance(message.get("tool_call"), dict):
            call = message["tool_call"]
            normalised.append(
                {
                    "role": "assistant",
                    "content": str(message.get("content") or ""),
                    "tool_calls": [
                        {
                            "id": str(call.get("id") or "call_0"),
                            "type": "function",
                            "function": {
                                "name": str(call.get("name") or ""),
                                "arguments": _json.dumps(
                                    call.get("arguments") or {}, separators=(",", ":")
                                ),
                            },
                        }
                    ],
                }
            )
        elif role == "assistant" and isinstance(message.get("tool_calls"), list):
            normalised.append({
                "role": "assistant", "content": str(message.get("content") or ""),
                "tool_calls": [{"id": str(call["id"]), "type": "function",
                                "function": {"name": str(call["name"]),
                                             "arguments": _json.dumps(call["arguments"])}}
                               for call in message["tool_calls"]],
            })
        elif role == "user" and message.get("tool_call_id") is not None:
            normalised.append(
                {
                    "role": "tool",
                    "tool_call_id": str(message["tool_call_id"]),
                    "content": str(message.get("content") or ""),
                }
            )
        else:
            normalised.append(
                {"role": role or "user", "content": str(message.get("content") or "")}
            )
    return normalised


def _normalise(raw: dict[str, Any], model_id: str) -> LLMResult:
    """Map an OpenAI-shaped response onto `LLMResult`."""
    choices = raw.get("choices") or []
    message: dict[str, Any] = choices[0].get("message") or {} if choices else {}
    tool_calls = [
        LLMToolCall(
            id=str(call.get("id") or f"call_{index:02d}"),
            name=str((call.get("function") or {}).get("name", "")),
            arguments=_as_dict((call.get("function") or {}).get("arguments")),
        )
        for index, call in enumerate(message.get("tool_calls") or [])
        if isinstance(call, dict)
    ]
    finish = str(choices[0].get("finish_reason") or "stop") if choices else "stop"
    usage = raw.get("usage") or {}
    return LLMResult(
        text=str(message.get("content") or ""),
        tool_calls=tool_calls,
        usage=LLMUsage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        ),
        model_id=model_id,
        stop_reason="tool_use" if tool_calls else _FINISH_REASONS.get(finish, "end_turn"),
        fallback=False,
    )


def _as_dict(value: Any) -> dict[str, Any]:
    """Arguments arrive as an object; some providers send a JSON string."""
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


def _hinted_seconds(exc: _RateLimited) -> float:
    try:
        return max(0.0, float(exc.retry_after_raw))
    except (TypeError, ValueError):
        return 0.0


def _parse_failed_generation(raw: str) -> dict[str, Any] | None:
    """Recover the tool call the model wanted from a `tool_use_failed` body."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("name"):
        return parsed
    return None
