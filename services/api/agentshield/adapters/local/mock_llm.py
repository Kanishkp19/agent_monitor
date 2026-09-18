"""Deterministic stand-in for a real model.

`MockLLMAdapter` replays scripted-but-realistic tool sequences per task type.
It is not a fallback of last resort -- it is the default provider, and the one
`advance()` forces regardless of configuration, because:

  * a demo that re-runs identically is a demo that can be rehearsed;
  * an evaluation harness needs the same event stream twice;
  * nineteen of twenty simulated employees do not need to be interesting.

Determinism rule: every draw comes from a `random.Random` seeded from
`(run seed, task id)`. Never module-level `random`, never wall time, never
`set` iteration order.

The real model still gets invoked for marquee sessions -- see
`SIM_LLM_INVOCATION_RATE`. Both travel the identical governance path, so the
telemetry is homogeneous either way.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agentshield.domain.enums import ToolName
from agentshield.ports.llm import LLMResult, LLMToolCall, LLMUsage

# Rough token accounting, so cost figures are plausible without a tokeniser.
_CHARS_PER_TOKEN = 4
_MIN_OUTPUT_TOKENS = 40


@dataclass(frozen=True)
class ScriptStep:
    """One assistant turn: either tool calls, or a closing message."""

    tools: tuple[tuple[ToolName, dict[str, Any]], ...] = ()
    text: str = ""


# One script per task type. Each ends with a text-only step, which is how the
# runner learns the task is finished.
_SCRIPTS: dict[str, tuple[ScriptStep, ...]] = {
    "bug_fix": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "src/handlers/payment.py"}),)),
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "unit"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.EDIT_FILE,
                    {"path": "src/handlers/payment.py", "diff": "@@ -42,1 +42,1 @@"},
                ),
            )
        ),
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "unit"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.GIT_COMMIT,
                    {"branch": "fix/payment-error", "message": "fix: handle null amount"},
                ),
            )
        ),
        ScriptStep(text="Fixed the null-amount path and the suite is green."),
    ),
    "unit_test": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "src/refund.py"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.EDIT_FILE,
                    {"path": "tests/test_refund.py", "diff": "+def test_partial_refund():"},
                ),
            )
        ),
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "unit"}),)),
        ScriptStep(text="Added coverage for the partial-refund path."),
    ),
    "documentation": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "README.md"}),)),
        ScriptStep(tools=((ToolName.EDIT_FILE, {"path": "README.md", "diff": "+## Refunds"}),)),
        ScriptStep(text="Documented the refund flow."),
    ),
    "api_work": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "src/api/routes.py"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.CALL_API,
                    {"service": "billing", "method": "GET", "path": "/v1/invoices"},
                ),
            )
        ),
        ScriptStep(
            tools=(
                (
                    ToolName.EDIT_FILE,
                    {"path": "src/api/routes.py", "diff": "+@router.get('/invoices')"},
                ),
            )
        ),
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "integration"}),)),
        ScriptStep(text="Wired the invoices endpoint."),
    ),
    "data_access": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "config/database.yaml"}),)),
        # The interesting one: a secret path. Gate 2 blocks it, the refusal
        # comes back as a tool result, and the model's next move is the signal.
        ScriptStep(tools=((ToolName.READ_FILE, {"path": ".env.production"}),)),
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "config/database.yaml"}),)),
        ScriptStep(text="Read the connection settings from the checked-in config."),
    ),
    "deployment": (
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "smoke"}),)),
        ScriptStep(tools=((ToolName.GIT_PUSH, {"branch": "main"}),)),
        ScriptStep(tools=((ToolName.DEPLOY, {"environment": "production"}),)),
        ScriptStep(text="Deployment requested."),
    ),
    "refactor": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "src/services/ledger.py"}),)),
        ScriptStep(
            tools=(
                (ToolName.EDIT_FILE, {"path": "src/services/ledger.py", "diff": "-class Ledger:"}),
            )
        ),
        ScriptStep(tools=((ToolName.RUN_TESTS, {"suite": "unit"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.GIT_COMMIT,
                    {"branch": "refactor/ledger", "message": "refactor: rename Ledger"},
                ),
            )
        ),
        ScriptStep(text="Renamed the class and updated call sites."),
    ),
    "incident_response": (
        ScriptStep(tools=((ToolName.READ_FILE, {"path": "logs/error.log"}),)),
        ScriptStep(
            tools=(
                (
                    ToolName.CALL_API,
                    {"service": "monitoring", "method": "GET", "path": "/alerts/active"},
                ),
            )
        ),
        ScriptStep(
            tools=(
                (
                    ToolName.EDIT_FILE,
                    {"path": "src/handlers/retry.py", "diff": "+backoff = min(2 ** n, 30)"},
                ),
            )
        ),
        ScriptStep(tools=((ToolName.DEPLOY, {"environment": "staging"}),)),
        ScriptStep(text="Mitigated with capped backoff, deployed to staging."),
    ),
}

_DEFAULT_SCRIPT = _SCRIPTS["bug_fix"]


class MockLLMAdapter:
    """Seeded, instant, free. Satisfies LLMPort."""

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model: str,
        max_tokens: int = 2048,
    ) -> LLMResult:
        task_type = _task_type_from(messages)
        script = _SCRIPTS.get(task_type, _DEFAULT_SCRIPT)

        # The conversation itself carries the iteration index: one assistant
        # turn per prior step. No hidden state, so the same messages always
        # produce the same answer -- including on replay.
        step_index = sum(1 for m in messages if m.get("role") == "assistant")
        step = (
            script[step_index]
            if step_index < len(script)
            else ScriptStep(text="Nothing further to do.")
        )

        rng = random.Random(self._seed ^ _stable_hash(_conversation_key(messages, step_index)))
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        input_tokens = max(1, prompt_chars // _CHARS_PER_TOKEN)
        output_tokens = _MIN_OUTPUT_TOKENS + rng.randrange(0, 160)

        tool_calls = [
            LLMToolCall(
                id=f"call_{step_index:02d}_{i:02d}",
                name=str(name),
                arguments=dict(args),
            )
            for i, (name, args) in enumerate(step.tools)
        ]

        return LLMResult(
            text=step.text,
            tool_calls=tool_calls,
            usage=LLMUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            model_id=f"mock:{model}",
            stop_reason="tool_use" if tool_calls else "end_turn",
            fallback=False,
        )


def _task_type_from(messages: Sequence[dict[str, Any]]) -> str:
    """Recover the task type the runner declared in its prompt.

    `agent/prompts.py` embeds `task_type=<value>` in the opening user message
    precisely so the mock can branch on it without a side channel.
    """
    for message in messages:
        content = str(message.get("content", ""))
        marker = "task_type="
        if marker in content:
            tail = content.split(marker, 1)[1]
            return tail.split()[0].strip().strip(".,;:")
    return "bug_fix"


def _conversation_key(messages: Sequence[dict[str, Any]], step_index: int) -> str:
    first = str(messages[0].get("content", "")) if messages else ""
    return f"{first[:200]}|{step_index}"


def _stable_hash(value: str) -> int:
    """`hash()` is salted per process, which would break reproducibility across
    runs. FNV-1a is boring and identical everywhere.
    """
    h = 0x811C9DC5
    for byte in value.encode("utf-8"):
        h = ((h ^ byte) * 0x01000193) & 0xFFFFFFFF
    return h
