#!/usr/bin/env python
"""Claude Code PreToolUse hook -> AgentShield gate.

Wire into `.claude/settings.json`:

    {"hooks": {"PreToolUse": [{"matcher": "Bash|Read|Edit|Write",
        "hooks": [{"type": "command",
                   "command": "python infra/scripts/claude_hook.py"}]}]}}

Claude Code sends the tool call as JSON on stdin. This script maps it onto
AgentShield's eight tools, asks the gate, and answers with Claude Code's
native decision shape:

    allow          -> {"decision": "allow"}                    (session proceeds)
    block          -> {"decision": "deny", "hookSpecificOutput":
                       {"permissionDecisionReason": "..."}}    (call is refused)
    review/redact  -> treated as deny for pre-tool hooks, with the reason

Fail-safe: if AgentShield is unreachable the hook ALLOWS with a note -- a
monitoring outage must not freeze a developer's session (governance itself
fails closed; this hook is a convenience tap on top of it, not the enforcer).

Env: AGENTSHIELD_URL (default http://localhost:8000),
     AGENTSHIELD_ROLE (default engineering_intern -- the persona you are
     governed as; set e.g. devops for prod privileges).
"""

from __future__ import annotations

import json
import os
import sys
from urllib import request as _urlrequest
from urllib.error import URLError

API = os.environ.get("AGENTSHIELD_URL", "http://localhost:8000").rstrip("/")
ROLE = os.environ.get("AGENTSHIELD_ROLE", "engineering_intern")

# Claude Code tool -> (AgentShield tool, argument mapping)
_MAP = {
    "Read": ("read_file", lambda i: {"path": i.get("file_path", ""), "repo": _repo(i)}),
    "Edit": ("edit_file", lambda i: {"path": i.get("file_path", ""), "diff": i.get("new_string", ""), "repo": _repo(i)}),
    "Write": ("edit_file", lambda i: {"path": i.get("file_path", ""), "diff": str(i.get("content", ""))[:400], "repo": _repo(i)}),
    "Bash": ("call_api", lambda i: {"command": str(i.get("command", ""))[:200]}),
    "WebFetch": ("external_fetch", lambda i: {"url": i.get("url", "")}),
    "Task": ("deploy", lambda i: {"environment": "staging" if "deploy" in str(i).lower() else "local"}),
}


def _repo(tool_input: dict) -> str:
    cwd = str(tool_input.get("cwd") or os.getcwd())
    return os.path.basename(cwd) or "payments-api"


def _allow(note: str = "") -> int:
    out: dict = {"decision": "allow"}
    if note:
        out["agentshield"] = note
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _deny(reason: str, policy: str | None = None) -> int:
    out = {
        "decision": "deny",
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecisionReason": f"AgentShield ({policy or 'governance'}): {reason}",
        },
    }
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return _allow("unparseable hook input; not governing")

    tool_name = str(event.get("tool_name", ""))
    tool_input = event.get("tool_input") or {}
    mapped = _MAP.get(tool_name)
    if mapped is None:
        return _allow()  # unmapped tool: nothing to govern here

    shield_tool, arg_mapper = mapped
    try:
        args = arg_mapper(tool_input)
    except Exception:  # noqa: BLE001 -- a mapping bug must never block a dev
        return _allow("argument mapping failed; not governing")

    payload = {
        "mode": "demo",
        "role": ROLE,
        "task": str(event.get("session_id", "Claude Code session"))[:120],
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
        return _allow(f"AgentShield unreachable ({exc}); not governing")

    data = body.get("data") or {}
    decision = str(data.get("decision", "allow"))
    reason = str(data.get("reason", ""))
    policy = (data.get("policy_ids") or [None])[0]

    if decision == "allow":
        # The sandbox already executed the simulated call; hand the output
        # back so the model keeps its tool result without a second round trip.
        result = data.get("result") or {}
        note = json.dumps(result)[:400] if result else ""
        return _allow(note)

    return _deny(reason, policy)


if __name__ == "__main__":
    sys.exit(main())
