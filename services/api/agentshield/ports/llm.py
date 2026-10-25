"""LLMPort -- the model boundary.

`LLMResult` deliberately mirrors the Bedrock Converse response shape. That is
the "adopt the model" half of the portability principle: the local Ollama
adapter does the translation work into this shape, so the domain never learns
that two different providers exist.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

StopReason = Literal["end_turn", "tool_use", "max_tokens", "error"]


class LLMUnavailable(Exception):
    """A live provider could not answer after bounded retries.

    Raised by adapters whose contract forbids mock substitution -- a caller
    that needs a *real* model run (Autopilot) must fail loudly rather than
    continue on scripted output. The simulation never catches this: it uses
    providers that degrade to MockLLM instead.
    """


class LLMNotConfigured(LLMUnavailable):
    """The live provider has no credentials configured."""


class LLMProviderError(LLMUnavailable):
    """The provider rejected the call (auth, model id, bad request).

    Carries the HTTP status so the operator can tell a wrong key from a
    wrong model id without re-running the request.
    """

    def __init__(self, message: str, *, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class LLMToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class LLMResult(BaseModel):
    # `model_id` is the Bedrock Converse field name and we adopt it verbatim.
    # Pydantic reserves the `model_` prefix by default; the shape matters more
    # than the warning.
    model_config = ConfigDict(protected_namespaces=())

    text: str
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    usage: LLMUsage
    model_id: str
    stop_reason: StopReason
    fallback: bool = False
    """True when the real provider was unreachable and MockLLM answered instead.

    Surfaced on `model.invoked` so a demo never silently reports fabricated
    numbers as real ones. The simulation must never stall waiting on a model.
    """


@runtime_checkable
class LLMPort(Protocol):
    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult: ...
