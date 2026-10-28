#!/usr/bin/env python
"""Codex CLI / generic exit-code approval hook -> AgentShield gate.

Usage in any agent that approves shell commands by exit code:

    <agent> -> runs: python codex_hook.py <tool> [key=value ...]

Exit codes:
    0 allow (prints the sandbox result if one exists)
    1 block (prints the reason and the matched policy)

The same script works for Codex (`~/.codex/config.toml` tool approvals),
Antigravity command hooks, or plain shell wrappers. It is the simplest
possible integration: one process, one argv, one exit code.

Env: AGENTSHIELD_URL (default http://localhost:8000),
     AGENTSHIELD_ROLE (default engineering_intern).
"""

from __future__ import annotations

import json
import os
import sys
from urllib import request as _urlrequest
from urllib.error import URLError

API = os.environ.get("AGENTSHIELD_URL", "http://localhost:8000").rstrip("/")
ROLE = os.environ.get("AGENTSHIELD_ROLE", "engineering_intern")

# <agent tool> -> (AgentShield tool, which argv item is which argument)
TOOL_MAP = {
    "read": ("read_file", "path"),
    "cat": ("read_file", "path"),
    "edit": ("edit_file", "path"),
    "write": ("edit_file", "path"),
    "test": ("run_tests", "suite"),
    "commit": ("git_commit", "message"),
    "push": ("git_push", "branch"),
    "deploy": ("deploy", "environment"),
    "fetch": ("external_fetch", "url"),
    "curl": ("external_fetch", "url"),
    "api": ("call_api", "path"),
}


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: codex_hook.py <tool> [key=value ...]", file=sys.stderr)
        return 1

    agent_tool = sys.argv[1].lower().lstrip("./")
    mapped = TOOL_MAP.get(agent_tool)
    if mapped is None:
        print(f"allow (tool {agent_tool!r} not governed by AgentShield)")
        return 0

    shield_tool, primary = mapped
    args: dict[str, str] = {}
    for token in sys.argv[2:]:
        key, _, value = token.partition("=")
        if _:
            args[key] = value
    if not args and len(sys.argv) > 2:
        args[primary] = sys.argv[2]

    payload = {
        "mode": "demo",
        "role": ROLE,
        "task": "Codex CLI session",
        "tool": shield_tool,
        "args": args,
    }
    request = _urlrequest.Request(
        f"{API}/api/v1/playground/hook/agent",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _urlrequest.urlopen(request, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
    except URLError as exc:
        # Monitoring outage: allow, loudly, rather than freeze the developer.
        print(f"allow (AgentShield unreachable: {exc})")
        return 0

    data = body.get("data") or {}
    decision = str(data.get("decision", "allow"))
    reason = str(data.get("reason", ""))
    policies = data.get("policy_ids") or []

    if decision == "block":
        print(f"BLOCKED by AgentShield [{', '.join(policies)}]: {reason}", file=sys.stderr)
        return 1
    if decision in ("review", "redact"):
        print(f"HOLD ({decision}) by AgentShield: {reason}", file=sys.stderr)
        return 1

    result = data.get("result") or {}
    if result:
        print(json.dumps(result)[:2000])
    else:
        print("allow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
