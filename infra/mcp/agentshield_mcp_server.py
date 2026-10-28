#!/usr/bin/env python
"""AgentShield MCP server (stdio, JSON-RPC 2.0, stdlib only -- no deps to install).

Gives a coding agent first-class tools over THIS project instead of raw shell:

    agentshield_graph_query   query docs/graph/graph.json (nodes, edges, layers, neighbours)
    agentshield_task          run whitelisted `python tasks.py` targets and return output
    agentshield_api           call the running API (healthz/readyz/metrics/risk/policies/...)
    agentshield_docs          keyword search across docs/ and the graph

Run:  python infra/mcp/agentshield_mcp_server.py
Config: see .mcp.json at the repo root.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib import request as _urlrequest
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "docs" / "graph" / "graph.json"
DOCS_DIRS = (ROOT / "docs", ROOT / "scenarios")

API_BASE = "http://localhost:8000"

# tasks.py targets it is safe for an agent to invoke, with arg rules.
# Anything not listed here is refused -- the server must never become a shell.
TASK_ALLOWLIST: dict[str, list[str]] = {
    "seed": [],
    "seed-policies": [],
    "seed-history": [],
    "advance": ["--days"],
    "demo": ["--seed"],
    "train-risk": [],
    "evaluate": [],
    "export-dataset": [],
    "inspect-events": ["--run-id", "--limit"],
    "check-secrets": [],
    "repro-check": [],
    "test": [],
    "test-contract": [],
    "test-web": [],
    "typecheck": [],
    "lint": [],
    "lint-web": [],
    "contracts": [],
    "atlas": [],
}

API_GET_ALLOWLIST = (
    "/healthz",
    "/readyz",
    "/api/v1/sim/runs",
    "/api/v1/events",
    "/api/v1/approvals",
    "/api/v1/risk/employees",
    "/api/v1/risk/weights",
    "/api/v1/incidents",
    "/api/v1/policies",
    "/api/v1/metrics/summary",
    "/api/v1/metrics/spend",
)


def _load_graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────────────


def tool_graph_query(args: dict) -> dict:
    """Query the codebase graph: lookup, search, neighbours, paths summary."""
    graph = _load_graph()
    nodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    mode = args.get("mode", "search")
    out: dict[str, object] = {"graph": graph.get("graph"), "invariants": graph["metadata"]["invariants"]}

    if mode == "node":
        node_id = str(args.get("id", ""))
        if node_id not in nodes:
            raise ValueError(f"unknown node id {node_id!r}; use mode=search")
        out["node"] = nodes[node_id]
        out["edges_out"] = [e for e in edges if e["from"] == node_id]
        out["edges_in"] = [e for e in edges if e["to"] == node_id]
        return out

    if mode == "neighbours":
        node_id = str(args.get("id", ""))
        if node_id not in nodes:
            raise ValueError(f"unknown node id {node_id!r}")
        related = sorted(
            {e["to"] for e in edges if e["from"] == node_id}
            | {e["from"] for e in edges if e["to"] == node_id}
        )
        out["node"] = nodes[node_id]
        out["neighbours"] = [
            {"id": rid, "label": nodes[rid]["label"], "layer": nodes[rid]["layer"]} for rid in related if rid in nodes
        ]
        return out

    if mode == "layer":
        layer = str(args.get("layer", ""))
        matches = [n for n in graph["nodes"] if n.get("layer") == layer]
        out["layer"] = layer
        out["nodes"] = [{"id": n["id"], "type": n["type"], "label": n["label"], "path": n.get("path")} for n in matches]
        out["count"] = len(matches)
        return out

    # mode == "search" (default): substring over id/label/path/summary
    needle = str(args.get("query", "")).lower()
    if not needle:
        raise ValueError("query is required for mode=search")
    hits = []
    for n in graph["nodes"]:
        hay = " ".join(str(n.get(k, "")) for k in ("id", "label", "path", "summary", "layer", "type")).lower()
        if needle in hay:
            hits.append({"id": n["id"], "label": n["label"], "layer": n.get("layer"), "path": n.get("path")})
    out["query"] = needle
    out["matches"] = hits[:25]
    out["count"] = len(hits)
    return out


def tool_task(args: dict) -> dict:
    """Run a whitelisted tasks.py target with validated flags; return output."""
    target = str(args.get("target", ""))
    if target not in TASK_ALLOWLIST:
        raise ValueError(
            f"target {target!r} is not allowlisted. Allowed: {', '.join(sorted(TASK_ALLOWLIST))}"
        )
    allowed_flags = TASK_ALLOWLIST[target]
    cmd = [sys.executable, str(ROOT / "tasks.py"), target]
    for key, value in (args.get("args") or {}).items():
        flag = f"--{key}"
        if flag not in allowed_flags:
            raise ValueError(f"flag {flag!r} is not allowed for target {target!r} (allowed: {allowed_flags})")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", str(value)):
            raise ValueError(f"unsafe value for {flag}: {value!r}")
        cmd += [flag, str(value)]

    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=int(args.get("timeout_seconds", 300)),
    )
    return {
        "target": target,
        "exit_code": proc.returncode,
        "stdout": proc.stdout[-12000:],
        "stderr": proc.stderr[-4000:],
    }


def tool_api(args: dict) -> dict:
    """GET a whitelisted endpoint from the running API (default :8000)."""
    path = str(args.get("path", "/healthz"))
    if not path.startswith(API_GET_ALLOWLIST):
        raise ValueError(f"path {path!r} is not allowlisted for GET. Allowed prefixes: {API_GET_ALLOWLIST}")
    run_id = args.get("run_id")
    url = f"{args.get('base', API_BASE)}{path}"
    if run_id and "?" not in path:
        url += f"?run_id={run_id}"
    try:
        with _urlrequest.urlopen(url, timeout=int(args.get("timeout_seconds", 10))) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return {"status": 200, "body": json.loads(body)}
    except URLError as exc:
        return {"status": 0, "error": f"API not reachable at {url}: {exc}"}


def tool_gate(args: dict) -> dict:
    """Ask AgentShield whether an action is allowed -- the integration point.

    One POST to `/api/v1/playground/hook/agent`. In `demo` mode the agent is
    governed as the named role (no key needed); in `live` mode an ingest
    bearer token resolves the identity server-side. The returned `decision`
    is the contract: `block` means do not proceed, `review` means wait for
    the approval_id, `allow` (with `result`) means the sandbox already
    executed the call.
    """
    payload = {
        "mode": args.get("mode", "demo"),
        "role": args.get("role", "engineering_intern"),
        "task": str(args.get("task", "Agent task"))[:120],
        "task_type": args.get("task_type", "bug_fix"),
        "complexity": args.get("complexity", "standard"),
        "repo": args.get("repo", "payments-api"),
        "environment": args.get("environment", "local"),
    }
    for key in ("prompt", "requested_model", "tool", "task_id"):
        if args.get(key) is not None:
            payload[key] = args[key]
    if isinstance(args.get("args"), dict):
        payload["args"] = args["args"]
    if "iteration" in args:
        payload["iteration"] = int(args["iteration"])

    headers = {"Content-Type": "application/json"}
    token = str(args.get("token") or "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{args.get('base', API_BASE)}/api/v1/playground/hook/agent"
    request = _urlrequest.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with _urlrequest.urlopen(request, timeout=int(args.get("timeout_seconds", 30))) as resp:
            return {"status": resp.status, **json.loads(resp.read().decode("utf-8", errors="replace"))}
    except URLError as exc:
        body = getattr(exc, "read", lambda: b"")()
        text = body.decode("utf-8", errors="replace") if body else str(exc)
        # A governed refusal may arrive as a 4xx -- the decision is the answer,
        # not an error. Only transport failure is reported as an error.
        try:
            return {"status": getattr(exc, "code", 0), **json.loads(text)}
        except (json.JSONDecodeError, ValueError):
            return {"status": 0, "error": f"AgentShield API not reachable at {url}: {exc}"}


def tool_docs(args: dict) -> dict:
    """Keyword search across docs/, scenarios/ and the graph summary."""
    query = str(args.get("query", "")).lower()
    if len(query) < 3:
        raise ValueError("query must be at least 3 characters")
    limit = int(args.get("limit", 12))
    results: list[dict] = []
    for directory in DOCS_DIRS:
        for md in sorted(directory.rglob("*.md")) + sorted(directory.rglob("*.yaml")):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lowered = text.lower()
            if query in lowered:
                idx = lowered.find(query)
                snippet = text[max(0, idx - 120) : idx + 240].replace("\n", " ")
                results.append({"file": str(md.relative_to(ROOT)), "snippet": snippet})
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return {"query": query, "matches": results, "count": len(results)}


TOOLS = [
    {
        "name": "agentshield_graph_query",
        "description": (
            "Query the AgentShield codebase graph (docs/graph/graph.json). Modes: "
            "search (keyword over id/label/path/summary), node (id + in/out edges), "
            "neighbours (adjacent components), layer (list one layer). Use this to "
            "orient before editing: which gate talks to which store, what guards what."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["search", "node", "neighbours", "layer"]},
                "query": {"type": "string"},
                "id": {"type": "string"},
                "layer": {"type": "string"},
            },
        },
    },
    {
        "name": "agentshield_task",
        "description": (
            "Run a whitelisted `python tasks.py` target (seed, seed-history, advance, demo, "
            "evaluate, check-secrets, repro-check, tests, lint, typecheck, contracts, ...) "
            "and capture stdout/stderr. Only allowlisted targets/flags are accepted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "args": {"type": "object", "additionalProperties": {"type": "string"}},
                "timeout_seconds": {"type": "integer"},
            },
            "required": ["target"],
        },
    },
    {
        "name": "agentshield_api",
        "description": (
            "GET a whitelisted endpoint from the running AgentShield API "
            "(/healthz, /readyz, /api/v1/sim/runs, events, approvals, risk, incidents, "
            "policies, metrics). Pass run_id where required."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "run_id": {"type": "string"},
                "base": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
        },
    },
    {
        "name": "agentshield_gate",
        "description": (
            "Ask the AgentShield governance plane whether an action is allowed "
            "BEFORE doing it. Call with a `prompt` for request governance (gate 1: "
            "secret redaction, budget, model routing) or with `tool` + `args` for "
            "action governance (gate 2: policy decision and simulated sandbox "
            "execution). Decision values: allow | redact | review | block. In demo "
            "mode you are governed as `role` (default engineering_intern); in live "
            "mode pass the ingest `token`. Treat `block` as a hard stop and `review` "
            "as wait-for-approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["demo", "live"]},
                "role": {
                    "type": "string",
                    "description": "demo mode persona: engineering_intern | engineer | senior_engineer | manager | devops",
                },
                "token": {"type": "string", "description": "live-mode ingest bearer token"},
                "prompt": {"type": "string", "description": "gate 1: the request text before the model call"},
                "requested_model": {"type": "string"},
                "tool": {
                    "type": "string",
                    "description": "gate 2: read_file | edit_file | run_tests | git_commit | git_push | call_api | deploy | external_fetch",
                },
                "args": {"type": "object"},
                "task_id": {"type": "string"},
                "task": {"type": "string"},
                "task_type": {"type": "string"},
                "complexity": {"type": "string", "enum": ["trivial", "standard", "complex"]},
                "repo": {"type": "string"},
                "environment": {"type": "string", "enum": ["local", "staging", "production"]},
                "iteration": {"type": "integer"},
                "base": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
        },
    },
    {
        "name": "agentshield_docs",
        "description": "Keyword search across docs/ and scenarios/ with file + snippet results.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
    },
]

HANDLERS = {
    "agentshield_graph_query": tool_graph_query,
    "agentshield_task": tool_task,
    "agentshield_api": tool_api,
    "agentshield_gate": tool_gate,
    "agentshield_docs": tool_docs,
}


# ──────────────────────────────────────────────────────────────────────
# MCP stdio plumbing (JSON-RPC 2.0)
# ──────────────────────────────────────────────────────────────────────


def _reply(msg_id: object, result: dict) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def _error(msg_id: object, code: int, message: str) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}) + "\n")
    sys.stdout.flush()


def _dispatch(msg_id: object, method: str, params: dict) -> None:
    if method == "initialize":
        _reply(
            msg_id,
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "agentshield", "version": "1.0.0"},
            },
        )
        return
    if method == "tools/list":
        _reply(msg_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = str(params.get("name", ""))
        handler = HANDLERS.get(name)
        if handler is None:
            _error(msg_id, -32602, f"unknown tool {name!r}")
            return
        try:
            result = handler(params.get("arguments") or {})
            _reply(
                msg_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, indent=2, default=str)}
                    ]
                },
            )
        except Exception as exc:  # tool errors surface as content, not protocol errors
            _reply(
                msg_id,
                {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                },
            )
        return
    if method.startswith("notifications/"):
        return  # notifications have no reply
    _error(msg_id, -32601, f"method not found: {method}")


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _error(None, -32700, "parse error")
            continue
        _dispatch(msg.get("id"), str(msg.get("method", "")), msg.get("params") or {})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
