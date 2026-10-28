# AgentShield MCP server

A dependency-free [Model Context Protocol](https://modelcontextprotocol.io) server over
stdio that gives a coding agent first-class tools for **this project** — instead of
raw shell access. Python stdlib only; nothing to install.

Registered at [`.mcp.json`](../.mcp.json) as server `agentshield`.

## Tools

| Tool | What it does |
|---|---|
| `agentshield_graph_query` | Query [`docs/graph/graph.json`](../docs/graph/graph.json): `search` (keyword), `node` (id + in/out edges), `neighbours`, `layer`. Use it to orient before editing — which gate talks to which store, what guards what. |
| `agentshield_task` | Run a **whitelisted** `python tasks.py` target and capture output. Allowed targets: `seed, seed-policies, seed-history, advance, demo, train-risk, evaluate, export-dataset, inspect-events, check-secrets, repro-check, test, test-contract, test-web, typecheck, lint, lint-web, contracts, atlas`. Flags are per-target allowlisted and value-checked. Everything else is refused. |
| `agentshield_api` | GET a whitelisted read endpoint from the running API (`/healthz`, `/readyz`, `/api/v1/sim/runs`, events, approvals, risk, incidents, policies, metrics). Returns a clean error when the API is down. |
| `agentshield_docs` | Keyword search across `docs/` and `scenarios/` with snippets. |

## Manual smoke test

```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python infra/mcp/agentshield_mcp_server.py
```

## Safety notes

- The task runner allowlist deliberately excludes destructive targets (`clean`) and the
  dev servers (`dev`, `api`, `web`) — long-running or destructive work stays with the
  human/agent shell.
- `advance`, `demo`, `evaluate`, `export-dataset` write to `.data/` only; they never
  touch source.
- The API tool is read-only GET on a fixed prefix list.
