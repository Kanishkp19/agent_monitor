"""Model selection and pricing.

`PRICE_TABLE` is the single source for every cost figure in the product --
the estimate Gate 1 makes before the call, the actual charged after it, the
exec view's spend, the Policy Lab's projected savings. One table means those
four numbers can never disagree, which matters because the Policy Lab's whole
claim is "this rule would have saved $21.40".

A policy can force a cheaper model via `route_override`. That is exactly the
"interns may not use frontier models for trivial work" rule, and it is how the
Policy Lab demonstrates savings without blocking anybody.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Complexity = Literal["trivial", "standard", "complex"]


@dataclass(frozen=True)
class ModelPrice:
    model_id: str
    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million / 1_000_000
            + output_tokens * self.output_per_million / 1_000_000
        )


# Real per-token prices for the models actually used. Figures are labelled
# "simulated spend" in the UI -- nothing is billed -- but they are real rates
# applied to real or simulated token counts, not invented numbers.
PRICE_TABLE: dict[str, ModelPrice] = {
    "anthropic.claude-3-5-haiku-20241022-v1:0": ModelPrice(
        "anthropic.claude-3-5-haiku-20241022-v1:0", 0.80, 4.00
    ),
    "anthropic.claude-3-5-sonnet-20241022-v2:0": ModelPrice(
        "anthropic.claude-3-5-sonnet-20241022-v2:0", 3.00, 15.00
    ),
    # Local models cost nothing to run, but they are priced at their cloud
    # equivalents so a local demo produces the same figures as a deployed one.
    # A demo whose numbers change when you move it is not a demo of anything.
    "qwen2.5-coder:1.5b": ModelPrice("qwen2.5-coder:1.5b", 0.80, 4.00),
    "qwen2.5-coder:7b": ModelPrice("qwen2.5-coder:7b", 0.80, 4.00),
    "mock:trivial": ModelPrice("mock:trivial", 0.80, 4.00),
    "mock:standard": ModelPrice("mock:standard", 0.80, 4.00),
    "mock:complex": ModelPrice("mock:complex", 3.00, 15.00),
    # Free cloud tiers (Groq's current catalog: gpt-oss). Nothing is billed at
    # these rates, but pricing them at their real cloud equivalents keeps the
    # cost story intact: a route_override that downgrades 120b -> 20b must
    # still show a real saving, and an unpriced model would punch a hole in
    # the spend figures.
    "openai/gpt-oss-20b": ModelPrice("openai/gpt-oss-20b", 0.80, 4.00),
    "openai/gpt-oss-120b": ModelPrice("openai/gpt-oss-120b", 3.00, 15.00),
    # Retired Groq ids, kept so historical telemetry still prices correctly.
    "llama-3.1-8b-instant": ModelPrice("llama-3.1-8b-instant", 0.80, 4.00),
    "llama-3.3-70b-versatile": ModelPrice("llama-3.3-70b-versatile", 3.00, 15.00),
}

# `docs/DESIGN.md` section 5.4.
ROUTING: dict[Complexity, str] = {
    "trivial": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "standard": "anthropic.claude-3-5-haiku-20241022-v1:0",
    "complex": "anthropic.claude-3-5-sonnet-20241022-v2:0",
}

LOCAL_ROUTING: dict[Complexity, str] = {
    "trivial": "qwen2.5-coder:1.5b",
    "standard": "qwen2.5-coder:7b",
    "complex": "qwen2.5-coder:7b",
}

# The hybrid brain serves free-cloud models. Priced at cloud rates so savings
# figures stay meaningful even though the tier itself is free.
HYBRID_ROUTING: dict[Complexity, str] = {
    "trivial": "openai/gpt-oss-20b",
    "standard": "openai/gpt-oss-20b",
    "complex": "openai/gpt-oss-120b",
}

# Rough token estimates per task type, used before the call. Being
# approximately right beforehand is what makes a budget guard possible at all;
# the actual figure replaces it the moment the model responds.
_ESTIMATED_TOKENS: dict[str, tuple[int, int]] = {
    "bug_fix": (1400, 600),
    "unit_test": (1100, 500),
    "documentation": (900, 700),
    "api_work": (1600, 700),
    "data_access": (1000, 400),
    "deployment": (800, 300),
    "refactor": (2000, 900),
    "incident_response": (1800, 800),
}

_COMPLEXITY_MULTIPLIER: dict[Complexity, float] = {
    "trivial": 0.5,
    "standard": 1.0,
    "complex": 2.2,
}


def route(
    complexity: Complexity,
    *,
    provider: str = "bedrock",
    override: str | None = None,
    requested: str | None = None,
) -> str:
    """Pick a model id.

    `override` comes from a matched policy and wins over everything -- that is
    the point of a route override. A caller's `requested_model` is honoured
    only if it is a model we actually price; otherwise the routing table
    decides, because an unpriced model would put a hole in the cost figures.
    """
    table = LOCAL_ROUTING if provider in ("ollama", "mock") else ROUTING
    if provider == "hybrid":
        table = HYBRID_ROUTING

    if override:
        resolved: Complexity = override if override in table else complexity  # type: ignore[assignment]
        return table[resolved]

    if requested and requested in PRICE_TABLE:
        return requested

    return table[complexity]


def price_for(model_id: str) -> ModelPrice:
    """Never raises: an unknown model is priced as the standard tier.

    A missing price must not be able to fail a governance decision. It would
    also silently understate spend if it returned zero, so it falls back to a
    real rate rather than to nothing.
    """
    if model_id in PRICE_TABLE:
        return PRICE_TABLE[model_id]
    for known, price in PRICE_TABLE.items():
        if model_id.endswith(known) or known.endswith(model_id):
            return price
    return PRICE_TABLE["anthropic.claude-3-5-haiku-20241022-v1:0"]


def cost_of(model_id: str, input_tokens: int, output_tokens: int) -> float:
    return price_for(model_id).cost(input_tokens, output_tokens)


def estimate_tokens(task_type: str, complexity: Complexity, prompt_len: int) -> tuple[int, int]:
    """Pre-flight token estimate, before a single token is spent."""
    base_in, base_out = _ESTIMATED_TOKENS.get(task_type, (1200, 500))
    multiplier = _COMPLEXITY_MULTIPLIER[complexity]
    # The prompt itself is known exactly; only the model's share is guessed.
    prompt_tokens = max(0, prompt_len // 4)
    return (
        int(base_in * multiplier) + prompt_tokens,
        int(base_out * multiplier),
    )
