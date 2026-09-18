"""The eight tools an agent may attempt.

Schemas are Bedrock Converse `toolSpec` shaped, because that is the format the
real provider wants and the local adapters translate *into* it. The list is
closed deliberately: a governance system that cannot enumerate the actions it
governs is a logging system.

Every one of these is individually governable by policy -- `action.tool` is in
the Gate 2 field allowlist.
"""

from __future__ import annotations

from typing import Any

from agentshield.domain.enums import ToolName


def _spec(name: ToolName, description: str, properties: dict[str, Any], required: list[str]):
    return {
        "name": str(name),
        "description": description,
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        },
    }


TOOL_SCHEMAS: list[dict[str, Any]] = [
    _spec(
        ToolName.READ_FILE,
        "Read a file from a repository.",
        {
            "repo": {"type": "string", "description": "Repository name"},
            "path": {"type": "string", "description": "Path within the repository"},
        },
        ["repo", "path"],
    ),
    _spec(
        ToolName.EDIT_FILE,
        "Apply a change to a file in a repository.",
        {
            "repo": {"type": "string"},
            "path": {"type": "string"},
            "diff": {"type": "string", "description": "Unified diff or replacement content"},
        },
        ["repo", "path", "diff"],
    ),
    _spec(
        ToolName.RUN_TESTS,
        "Run a test suite for a repository.",
        {
            "repo": {"type": "string"},
            "suite": {"type": "string", "description": "unit | integration | smoke | all"},
        },
        ["repo"],
    ),
    _spec(
        ToolName.GIT_COMMIT,
        "Commit staged changes to a branch.",
        {
            "repo": {"type": "string"},
            "branch": {"type": "string"},
            "message": {"type": "string"},
        },
        ["repo", "branch", "message"],
    ),
    _spec(
        ToolName.GIT_PUSH,
        "Push a branch to the remote.",
        {"repo": {"type": "string"}, "branch": {"type": "string"}},
        ["repo", "branch"],
    ),
    _spec(
        ToolName.CALL_API,
        "Call an internal service API.",
        {
            "service": {"type": "string"},
            "method": {"type": "string", "description": "GET | POST | PUT | DELETE"},
            "path": {"type": "string"},
            "environment": {"type": "string", "description": "local | staging | production"},
        },
        ["service", "method", "path"],
    ),
    _spec(
        ToolName.DEPLOY,
        "Deploy a repository to an environment.",
        {
            "repo": {"type": "string"},
            "environment": {"type": "string", "description": "local | staging | production"},
        },
        ["repo", "environment"],
    ),
    _spec(
        ToolName.EXTERNAL_FETCH,
        "Fetch a URL outside the corporate network.",
        {"url": {"type": "string"}},
        ["url"],
    ),
]

TOOL_NAMES: frozenset[str] = frozenset(str(t) for t in ToolName)


def schema_for(tool: ToolName | str) -> dict[str, Any] | None:
    name = str(tool)
    return next((s for s in TOOL_SCHEMAS if s["name"] == name), None)


def is_known(tool: str) -> bool:
    return tool in TOOL_NAMES


def coerce_tool(name: str) -> ToolName | None:
    """A model can hallucinate a tool name. That is not a crash.

    An unknown tool comes back to the model as a tool result saying so, the
    same way a blocked one does, and the loop continues.
    """
    try:
        return ToolName(name)
    except ValueError:
        return None
