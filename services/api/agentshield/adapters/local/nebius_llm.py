"""Nebius Token Factory implementation of LLMPort -- NVIDIA Nemotron.

Nebius serves OpenAI-compatible `/chat/completions`, so the wire translation
is shared with `openai_compat_llm` (history normalisation, tool-schema
mapping, response mapping). What deliberately differs is the failure
contract:

**No mock fallback. Ever.** The free-tier adapter degrades to MockLLM so the
office simulation never stalls -- correct for a game, wrong for an Autopilot
run whose entire value is that a real NVIDIA Nemotron model did the work.
Here, a missing key raises `LLMNotConfigured`, a provider rejection raises
`LLMProviderError`, and retryable failures that exhaust their budget raise
`LLMUnavailable`. The caller fails the job honestly; nothing is fabricated.

Retries exist only for the two transient classes (429 rate limit, 5xx /
transport), are bounded by `NEBIUS_MAX_RETRIES`, and back off exponentially
with a `Retry-After` hint taking precedence when the provider sends one.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import httpx

from agentshield.adapters.local.openai_compat_llm import (
    RateLimiter,
    _normalise,
    _normalise_messages,
)
from agentshield.ports.llm import (
    LLMNotConfigured,
    LLMProviderError,
    LLMResult,
    LLMUnavailable,
)

if TYPE_CHECKING:
    from agentshield.config import Settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504})

# A Nemotron answer can be long, but a tool-loop turn that returns 500 KB of
# text is a bug, not an answer. The cap keeps one malformed response from
# blowing the prompt budget; the full text stays in the provider logs.
_MAX_TEXT_CHARS = 32_000


class NebiusAdapter:
    """`/chat/completions` against Nebius, serving NVIDIA Nemotron."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._base_url = settings.nebius_base_url.rstrip("/")
        self._api_key = settings.nebius_api_key
        self._model = settings.nebius_model
        self._timeout = settings.nebius_timeout_seconds
        self._retries = settings.nebius_max_retries
        self._client = client
        self._limiter = limiter or RateLimiter(settings.nebius_rpm)

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        if not self._api_key:
            # Not an error the caller can retry; the deployment is missing a
            # secret. Never substituted, never guessed.
            raise LLMNotConfigured(
                "NEBIUS_API_KEY is not set; live Nemotron inference is not "
                "available and no mock substitution is permitted for Autopilot."
            )

        # `model` is a routing tier in the LLMPort contract; Autopilot passes
        # "standard"/"complex", and every tier is the configured Nemotron.
        payload = {
            "model": self._model,
            "messages": _normalise_messages(messages),
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = _nebius_tools(tools)

        last_error = ""
        for attempt in range(self._retries + 1):
            try:
                await self._limiter.acquire()
                raw = await self._post(payload)
                return _bounded(raw, self._model)
            except _RateLimited as exc:
                last_error = str(exc)
                if attempt >= self._retries:
                    break
                pause = max(_hinted_seconds(exc), 0.5 * (2**attempt))
                logger.warning(
                    "nebius rate limited; backing off %.1fs",
                    pause,
                    extra={"model": self._model, "attempt": attempt + 1},
                )
                await asyncio.sleep(pause)
            except _Retryable as exc:
                last_error = str(exc)
                if attempt >= self._retries:
                    break
                logger.warning(
                    "nebius transient error; retrying",
                    extra={"model": self._model, "attempt": attempt + 1, "error": last_error[:200]},
                )
                await asyncio.sleep(0.5 * (2**attempt))
            except _ProviderRejected as exc:
                raise LLMProviderError(str(exc), status=exc.status) from None
            except httpx.HTTPError as exc:
                last_error = repr(exc)
                if attempt >= self._retries:
                    break
                logger.warning(
                    "nebius transport error; retrying",
                    extra={"model": self._model, "attempt": attempt + 1, "error": last_error[:200]},
                )
                await asyncio.sleep(0.5 * (2**attempt))

        raise LLMUnavailable(
            f"nebius unavailable after {self._retries + 1} attempt(s): {last_error[:300]}"
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
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
        if response.status_code in _RETRYABLE_STATUS:
            raise _Retryable(response.status_code, response.text or "")
        if response.status_code >= 400:
            raise _ProviderRejected(response.status_code, response.text or "")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


class _RateLimited(Exception):
    def __init__(self, retry_after: str, body: str) -> None:
        super().__init__(f"rate limited (retry-after={retry_after!r}): {body[:200]}")
        self.retry_after_raw = retry_after


class _Retryable(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


class _ProviderRejected(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


def _nebius_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bedrock Converse `toolSpec` -> OpenAI `function` (same map as the
    free-tier adapter; a Nemotron tool call arrives in OpenAI shape)."""
    return [
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


def _bounded(raw: dict[str, Any], model_id: str) -> LLMResult:
    result = _normalise(raw, model_id)
    if len(result.text) > _MAX_TEXT_CHARS:
        result = result.model_copy(
            update={"text": result.text[:_MAX_TEXT_CHARS] + "\n…[truncated]"}
        )
    return result


def _hinted_seconds(exc: _RateLimited) -> float:
    try:
        return min(max(0.0, float(exc.retry_after_raw)), 30.0)
    except (TypeError, ValueError):
        return 0.0


__all__ = ["NebiusAdapter"]
