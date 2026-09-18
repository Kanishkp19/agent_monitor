"""Prompt construction and tool-result formatting.

The opening user message embeds `task_type=<value>`. That is not decoration:
`MockLLMAdapter` reads it to pick its script, which keeps the mock's behaviour
derived from the same prompt the real model sees rather than from a side
channel that could drift.

How a refusal is phrased matters more than it looks. A blocked tool call comes
back as a *tool result*, and the wording tells the model it was a policy
decision rather than a transient failure -- otherwise it retries the identical
call, which is both wasted spend and a false adversarial signal.
"""

from __future__ import annotations

import json
from typing import Any

from agentshield.domain.models import Task
from agentshield.ports.llm import LLMToolCall

SYSTEM_PROMPT = """\
You are a coding agent working inside a software company. You have tools for \
reading and editing files, running tests, committing and pushing code, calling \
internal APIs, deploying, and fetching external URLs.

Work in small steps. Read before you edit. Run tests after you change \
behaviour. When the task is done, reply with a short summary and no tool call.

Some actions are governed by company policy. If a tool returns \
`blocked_by_policy`, that is a deliberate decision, not a transient error: do \
not retry the same call. Either find another way to accomplish the task or \
explain what you would need.\
"""


def build_prompt(task: Task) -> str:
    """The opening user message.

    Machine-readable facts first (the mock parses them, and they keep the
    model anchored), then the human instruction.
    """
    return (
        f"task_type={task.task_type} "
        f"complexity={task.complexity} "
        f"repo={task.repo} "
        f"environment={task.environment}\n\n"
        f"{task.title}\n\n"
        f"Work in the {task.repo} repository."
    )


def assistant_tool_use(call: LLMToolCall, text: str = "") -> dict[str, Any]:
    """Record the assistant's turn, so the next iteration has the history."""
    return {
        "role": "assistant",
        "content": text or f"Calling {call.name}.",
        "tool_call": {"id": call.id, "name": call.name, "arguments": call.arguments},
    }


def tool_result_message(call_id: str, name: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "user",
        "content": f"[tool_result:{name}] {json.dumps(result, separators=(',', ':'))}",
        "tool_call_id": call_id,
    }


def blocked_result(reason: str, policy_id: str | None) -> dict[str, Any]:
    """What the agent sees when Gate 2 refuses.

    Returned as a tool result rather than raised as an exception. The agent's
    *reaction* to a block -- whether it adapts, gives up, or tries the same
    path five more ways -- is the richest adversarial signal the system has,
    and an exception would throw it away.
    """
    payload: dict[str, Any] = {"error": "blocked_by_policy", "reason": reason}
    if policy_id:
        payload["policy"] = policy_id
    return payload


def denied_result(reason: str) -> dict[str, Any]:
    return {"error": "approval_denied", "reason": reason}


def expired_result() -> dict[str, Any]:
    return {
        "error": "approval_expired",
        "reason": "No approver responded before the request timed out.",
    }


def unknown_tool_result(name: str) -> dict[str, Any]:
    return {
        "error": "unknown_tool",
        "reason": f"There is no tool called {name!r}. Use one of the provided tools.",
    }


def malformed_call_result(name: str, detail: str) -> dict[str, Any]:
    """One correction round-trip before the session is failed."""
    return {
        "error": "invalid_arguments",
        "reason": f"The arguments for {name} were not valid: {detail}",
    }
