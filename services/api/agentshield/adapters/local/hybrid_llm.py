"""Hybrid LLMPort: free cloud first, local Ollama second, Mock last.

The default brain for a real-bot office that must cost nothing:

    cloud (rate-limited)  ->  ollama (local, free)  ->  mock (scripted)

Each tier substitutes on the previous one's failure, and every substitution is
recorded on the result (`fallback=True`) so `model.invoked` telemetry stays
honest about whether a decision was a real model's or a scripted stand-in's.

Two deliberate properties:

**A circuit breaker, not a queue.** When the cloud tier fails outright the
adapter stops asking it for a quiet period instead of paying the timeout on
every call. The breaker is wall-clock state by construction -- a provider
outage is a real-world condition -- but it only decides *which* tier answers;
simulation time is untouched, and `advance()` still forces MockLLM regardless
of any of this. Sessions remain asynchronous: a caller never blocks on a
struggling tier longer than its own timeout.

**Which model, whose price.** The caller asks by complexity tier (`trivial`,
`standard`, `complex`); the winning tier names the concrete model id, and the
result carries the id actually used so `router.PRICE_TABLE` -- not the caller
-- decides the cost.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from agentshield.adapters.local.mock_llm import MockLLMAdapter
from agentshield.adapters.local.ollama_llm import OllamaAdapter
from agentshield.adapters.local.openai_compat_llm import OpenAICompatAdapter
from agentshield.ports.llm import LLMPort, LLMResult

if TYPE_CHECKING:
    from agentshield.config import Settings

logger = logging.getLogger(__name__)


class _Breaker:
    """Trip on repeated cloud failure, cool off, then probe again."""

    def __init__(self, threshold: int, cooldown_seconds: float) -> None:
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._consecutive = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        if self._consecutive < self._threshold:
            return True
        return (time.monotonic() - self._opened_at) >= self._cooldown

    def record_success(self) -> None:
        self._consecutive = 0

    def record_failure(self) -> None:
        if self._consecutive == 0:
            self._opened_at = time.monotonic()
        self._consecutive += 1


class HybridAdapter:
    """Cloud when available, Ollama when not, Mock when neither answers."""

    def __init__(
        self,
        settings: Settings,
        *,
        cloud: OpenAICompatAdapter | None = None,
        local: LLMPort | None = None,
    ) -> None:
        self._cloud: OpenAICompatAdapter | None = cloud or (
            OpenAICompatAdapter(settings) if settings.llm_cloud_api_key else None
        )
        # Any LLMPort can serve as the local tier; production wires the real
        # OllamaAdapter, tests inject whatever the scenario needs.
        self._local = local or OllamaAdapter(settings)
        self._fallback = MockLLMAdapter(seed=settings.sim_seed)
        self._breaker = _Breaker(
            threshold=settings.llm_cloud_breaker_threshold,
            cooldown_seconds=float(settings.llm_cloud_breaker_cooldown_s),
        )

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        if self._cloud is not None and self._breaker.allow():
            try:
                result = await self._cloud.complete(
                    messages=messages, tools=tools, model=model, max_tokens=max_tokens
                )
            except Exception:  # the tiers below must always be reachable
                logger.exception("cloud tier raised; trying local ollama")
                self._breaker.record_failure()
            else:
                if result.fallback:
                    # The cloud adapter already exhausted its retries (429s,
                    # outage). Count the failure so the breaker can skip this
                    # tier for a while -- but Ollama may still rescue the
                    # session with a real model, so fall through.
                    self._breaker.record_failure()
                    logger.warning("cloud tier degraded; trying local ollama")
                else:
                    self._breaker.record_success()
                    return result

        # Production wires OllamaAdapter here: a real local model when it is
        # up, its own honest mock substitution (`fallback=True`) when not.
        return await self._local.complete(
            messages=messages, tools=tools, model=model, max_tokens=max_tokens
        )

    @property
    def fallback(self) -> MockLLMAdapter:
        """The final tier, exposed for tests that need to seed it."""
        return self._fallback
