# Integrating real coding agents with AgentShield

AgentShield is the checkpoint between an AI coding agent and everything it
touches. Any tool that can make an HTTP call (or speak MCP) can be governed.
There is one universal endpoint and one decision contract:

```
POST /api/v1/playground/hook/agent
{
  "mode": "demo" | "live",
  "role": "engineering_intern",          # demo mode: which persona governs you
  "token": "<ingest-token>",             # live mode: server-side identity
  "prompt": "…",                         # gate 1: before a model call
  "tool": "read_file", "args": {…},      # gate 2: before a tool executes
  "task": "Fix the null-amount bug",
  "repo": "payments-api",
  "environment": "local"
}
```

**The decision contract** (identical to what the office simulation enforces):

| decision | what the agent must do |
|---|---|
| `allow` | proceed (for tool calls, `result` already contains the simulated sandbox output) |
| `redact` | use the returned, masked `prompt` — the raw value never leaves the caller |
| `review` | stop and wait for the `approval_id` (poll `GET /api/v1/approvals/{id}`) |
| `block` | hard stop — do not proceed; `reason` names the policy |

The governed role is part of the *credential*, never the body: in demo mode
`Bearer demo-<role>` (no sign-in, governed as that persona); in live mode a
real `INGEST_TOKENS` bearer whose actor is resolved server-side, so a
compromised agent cannot assert its own role.

---

## 1. Claude Code (hooks + MCP)

**Option A — a PreToolUse hook** (runs before *every* tool call, in
`.claude/settings.json` of the project):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python /path/to/Agent-Shield-/infra/scripts/claude_hook.py"
          }
        ]
      }
    ]
  }
}
```

The hook reads Claude Code's JSON on stdin (`tool_name`, `tool_input`,
`session_id`, `cwd`) and answers `{"decision": "allow"}` or
`{"decision": "deny", "hookSpecificOutput": {"permissionDecisionReason": …}}`
which Claude Code obeys natively. It maps Claude Code tools onto
AgentShield's eight, forwards to `/playground/hook/agent` and — when allowed
— returns the simulated sandbox output so the agent keeps working offline.
To *experience* a role's restrictions, set the role in the script
(`AGENTSHIELD_ROLE=engineering_intern`).

**Option B — the MCP server** (`.mcp.json` already ships in this repo):

```json
{ "mcpServers": { "agentshield": {
    "command": "python",
    "args": ["infra/mcp/agentshield_mcp_server.py"] } } }
```

Claude Code then has `agentshield_gate` as a first-class tool: "before you
deploy, ask agentshield_gate; if it says block, stop and tell me why."

---

## 2. Codex CLI (approvals + config)

Codex (`~/.codex/config.toml`) supports command approvals and MCP servers:

```toml
[mcp_servers.agentshield]
command = "python"
args = ["/path/to/Agent-Shield-/infra/mcp/agentshield_mcp_server.py"]

# Wrap a risky tool so Codex asks the gate before running it:
[tools.shell]
approve = ["python", "/path/to/Agent-Shield-/infra/scripts/codex_hook.py"]
```

`codex_hook.py` receives the command on argv, asks the gate, and exits 0
(allow) or 1 (block, printing the reason). Any agent that shells out can use
the same exit-code contract.

---

## 3. Antigravity / any browser IDE / anything with HTTP

Same endpoint, no SDK:

```bash
curl -X POST http://localhost:8000/api/v1/playground/hook/agent \
  -H "Content-Type: application/json" \
  -d '{"mode":"demo","role":"engineering_intern",
       "tool":"deploy","args":{"environment":"production"},
       "task":"Ship the hotfix"}'
```

Response: `{"decision":"block","reason":"Production deployment is not
available at this level.","policy_ids":["pol_intern_no_prod_deploy", …]}`.

Agents that speak MCP get the same via `agentshield_gate` (works in Antigravity,
Cursor, Windsurf, Zed, Continue — anything that supports MCP servers).

---

## 4. The tool mapping

AgentShield governs eight tools; map your agent's tools onto them:

| Agent tool | AgentShield tool | Notes |
|---|---|---|
| Read file / cat | `read_file` | secret paths (`.env*`, `secrets/`, `keys/`) trip gate 2 |
| Edit / write / patch | `edit_file` | takes `path` + `diff` |
| Run tests / tests | `run_tests` | takes `suite` |
| Commit | `git_commit` | takes `branch`, `message` |
| Push | `git_push` | protected branches trip the gate |
| HTTP call / fetch | `call_api` / `external_fetch` | `external_fetch` is allowlist-enforced |
| Deploy / ship / release | `deploy` | takes `environment`; role + approval rules apply |

---

## 5. Where the simulation ends

The sandbox is deliberate simulation: files live in the VFS (seeded trees
including real secret files, so blocking them is a genuine event), tests
produce seeded pass/fail, deploys touch nothing. **Governance is real** —
the same gates, policies, precedence, approvals and telemetry as production
AgentShield. Connecting a real executor later means implementing a new
`Sandbox` adapter behind the same port; the gates never change.
