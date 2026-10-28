# AgentShield — The Complete Operating Guide

> **What is this document?**
> The hands-on manual: how the system is wired (with diagrams), how to run and
> operate every part of it, how to integrate Claude Code / Codex / Antigravity
> / any MCP client, and how to test everything end to end — with expected
> outputs. Pair it with [`architecture.md`](./architecture.md) (the *why*) —
> this is the *how*.

---

## Table of contents

1. [The system on one page](#1-the-system-on-one-page)
2. [Run it — step by step](#2-run-it--step-by-step)
3. [Operate the office](#3-operate-the-office)
4. [Use the Sandbox](#4-use-the-sandbox)
5. [Write and change rules](#5-write-and-change-rules)
6. [Give the bots real AI brains](#6-give-the-bots-real-ai-brains)
7. [Integrate Claude Code](#7-integrate-claude-code)
8. [Integrate Codex CLI](#8-integrate-codex-cli)
9. [Integrate Antigravity / Cursor / any MCP client](#9-integrate-antigravity--cursor--any-mcp-client)
10. [Integrate anything else (raw HTTP)](#10-integrate-anything-else-raw-http)
11. [Test everything (with expected outputs)](#11-test-everything-with-expected-outputs)
12. [Where the data lives / reset](#12-where-the-data-lives--reset)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. The system on one page

```mermaid
flowchart TB
    subgraph RUN["🐳 What runs"]
        API["FastAPI · :8000<br/>gates · sim · risk · telemetry"]
        WEB["Vite + React · :5173<br/>office · sandbox · console"]
        OPT["optional: Ollama · :11434<br/>local AI brain"]
    end

    subgraph BRAINS["AI brain chain (hybrid)"]
        GROQ["☁️ Groq gpt-oss-20b/120b<br/>free cloud tier"]
        OLL["💻 Ollama local"]
        MOCK["📜 MockLLM (scripted, honest fallback)"]
    end

    subgraph UI["The web console (:5173)"]
        OFF["/office — digital twin"]
        LIVE["/live — event stream"]
        APPR["/approvals — human decisions"]
        SBX["/sandbox — no-sign-in playground"]
        CTRL["/control — policies · lab · risk · costs"]
    end

    subgraph INTEGRATIONS["Your coding agents"]
        CC["Claude Code<br/>PreToolUse hook"]
        CX["Codex CLI<br/>exit-code hook"]
        MCP["Any MCP client<br/>agentshield_gate"]
        RAW["Anything<br/>POST /playground/hook/agent"]
    end

    GROQ --> API
    OLL --> API
    MOCK --> API
    API --> OFF & LIVE & APPR & SBX & CTRL
    CC & CX & MCP & RAW --> API
    API --> WS["WebSocket /ws/stream"] --> UI
```

The mental model in one sentence: **one API process owns the rulebook and the
event stream; the browser renders it; your coding agents phone it in.**

---

## 2. Run it — step by step

```bash
cd Agent-Shield-

# First time only: venv + deps + .env (backend AND web)
python tasks.py setup

# Seed the world (deterministic from SIM_SEED)
python tasks.py seed           # 20 employees, 6 repos, 13 policies
python tasks.py seed-history   # +14 sim-days of history → risk baselines exist

# Run
python tasks.py dev            # API :8000 + web :5173 (Ctrl-C stops both)
```

> **macOS note:** if `python` is 3.9 (system), use `python3 tasks.py …` and let
> `setup` build the venv with a 3.11+ interpreter. If `.venv` was created on
> another OS (has `Scripts/` instead of `bin/`), delete
> `services/api/.venv` and re-run setup.

**Health check:**

```bash
curl http://localhost:8000/healthz
```

```json
{"status":"ok","env":"local","llm_provider":"hybrid",
 "adapters":{"docstore":"SqliteDocStore","blobs":"FsBlobStore",
             "llm":"HybridAdapter","clock":"SimClock", ...}}
```

`/healthz` names every adapter — after any config change, this is how you
*verify* what you're running rather than assume.

**Run without the office (API only):**

```bash
python tasks.py api
```

**Headless (no browser at all):**

```bash
python tasks.py demo          # deterministic 5-beat scripted demo
python tasks.py advance --days 7
```

---

## 3. Operate the office

Open **http://localhost:5173**.

| Action | How |
|---|---|
| Start / pause | **▶ REAL TIME / ⏸ PAUSE** in the header |
| Fast-forward | **▶▶ 10×** for hours in seconds; **100×** runs a batch with a progress dialog |
| Inspect an employee | Click their avatar → drawer with live counters, risk meter, current task, recent decisions |
| Watch decisions | **LIVE FEED** — every gate decision, block, and model call, ordered |
| Approve something | **APPROVALS** — pending `review` decisions wait here (and expire on sim-time TTL) |
| Who's risky? | **CONTROL → Risk** leaderboard, **Incidents** for the alarm list |

**The office is honest by construction:** it renders the event stream, it
holds no authority. Reload the page and it rehydrates from
`GET /api/v1/sim/runs/{id}/state` with no desync.

**Headless equivalents:**

```bash
python tasks.py inspect-events --limit 10         # peek at stored events
python tasks.py run-task --employee emp_013 --task "Fix payment API error" --env production
```

---

## 4. Use the Sandbox

Open **http://localhost:5173/sandbox** — **no sign-in**.

1. **Pick your role** — Engineering Intern, Engineer, Senior Engineer,
   Manager, DevOps. The persona (repos, prod access, budget) is copied from
   the real seeded employee of that role.
2. **Pick a model tier** (Auto lets the policy router decide) and a repo +
   environment.
3. **Type a prompt** → **Run through Gate 1**. The decision appears with its
   reason and matched policy ids. Try embedding a fake AWS key — watch it
   come back redacted.
4. **Attempt one tool call** — six one-click attempts (read `.env.production`,
   deploy → production, push main, …) go through Gate 2 and the simulated
   sandbox. Blocks show the exact policy that fired.

Everything you see runs through the *same* gates the office runs. Nothing to
configure, nothing to break.

**Same thing from the terminal:**

```bash
curl -X POST http://localhost:8000/api/v1/playground/gate1 \
  -H "Content-Type: application/json" -H "Authorization: Bearer demo-engineering_intern" \
  -d '{"role":"engineering_intern","task_type":"bug_fix","complexity":"standard",
       "repo":"payments-api","environment":"local",
       "prompt":"Fix the auth bug. AWS key is AKIAIOSFODNN7EXAMPLE."}'
```

---

## 5. Write and change rules

Rules are **policies** — JSON conditions over allowlisted fields with an
action. Two ways to change them:

**A. The UI (Control Center → Policies):** create, edit, toggle. Editing is
append-only — a PATCH creates version N+1 and the old version stays. The
editor validates as you type (unknown fields get "did you mean…?").

**B. The API:**

```bash
curl -X POST http://localhost:8000/api/v1/policies \
  -H "Content-Type: application/json" \
  -d '{"name":"no weekend deploys","gate":2,"action":"review",
       "priority":50,"approver_role":"manager",
       "when":{"field":"action.tool","op":"eq","value":"deploy"}}'
```

**Test before enforcing — the Policy Lab** (Control → Policy Lab): pick a
draft rule, replay it against recorded history, and read the numbers that
matter: *newly blocked previously-succeeded* (the false-positive proxy),
extra approvals/day, projected savings.

**Precedence is fixed:** `block > review > redact > allow`. Priority decides
*attribution* (which rule gets credit), never the outcome. A draft `allow`
can never override a live `block`.

Rule changes take effect for **everyone at once** — office bots, Sandbox
visitors, and your integrated Claude Code/Codex sessions.

---

## 6. Give the bots real AI brains

The brain chain is **cloud → local → mock**, configured in `.env`:

```env
LLM_PROVIDER=hybrid
LLM_CLOUD_API_KEY=gsk_…                       # free key: console.groq.com
LLM_CLOUD_MODEL_TRIVIAL=openai/gpt-oss-20b
LLM_CLOUD_MODEL_STANDARD=openai/gpt-oss-20b
LLM_CLOUD_MODEL_COMPLEX=openai/gpt-oss-120b
LLM_CLOUD_RPM=28                              # requests/min cap
SIM_LLM_INVOCATION_RATE=0.40                  # share of sessions that think for real
SIM_MAX_CONCURRENT_SESSIONS=2                 # stay under free-tier limits
```

Optional local tier (offline resilience):

```bash
brew install ollama && ollama serve &
ollama pull qwen2.5-coder:1.5b && ollama pull qwen2.5-coder:7b
```

**Verify the mix after a few minutes at 1×:**

```bash
sqlite3 .data/agentshield.db \
  "SELECT json_extract(body,'$.detail.payload.model_id') m,
          json_extract(body,'$.detail.payload.fallback') fb, COUNT(*)
   FROM items WHERE sk LIKE 'EVT#%'
     AND json_extract(body,'$.detail_type')='model.invoked'
   GROUP BY 1,2 ORDER BY 3 DESC LIMIT 6"
```

Expect mostly `openai/gpt-oss-20b | 0` (real), a little `mock:* | 1` (honest
fallback). Restart the API after changing `.env`.

**What you gain by going hybrid:** bots whose tool calls are genuinely chosen
by an LLM (through both gates), while volume stays high and the demo stays
free. **What never changes:** determinism for evaluation — `advance()` and
`seed-history` always force the seeded MockLLM.

---

## 7. Integrate Claude Code

Two options; use both if you like.

### Option A — PreToolUse hook (every tool call governed)

Create `.claude/settings.json` in your project:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|Bash|WebFetch",
        "hooks": [
          {
            "type": "command",
            "command": "python /absolute/path/to/Agent-Shield-/infra/scripts/claude_hook.py"
          }
        ]
      }
    ]
  }
}
```

Set the persona you want to be governed as:

```bash
export AGENTSHIELD_ROLE=engineering_intern     # or engineer, devops, …
export AGENTSHIELD_URL=http://localhost:8000
```

Now every time Claude Code tries a tool, the hook asks AgentShield first:

- **blocked** → Claude Code refuses the call and shows the policy reason
- **allowed** → proceeds (the hook also returns the simulated sandbox output,
  so a Read of `src/payment.py` "works")

Fail-open note: if the AgentShield API is down, the hook *allows* with a note
— a monitoring outage must not freeze a developer. The gates themselves still
fail closed.

### Option B — MCP server (ask-the-gate as a tool)

Add to `.mcp.json` (already ships in this repo):

```json
{ "mcpServers": { "agentshield": {
    "command": "python",
    "args": ["/path/to/Agent-Shield-/infra/mcp/agentshield_mcp_server.py"] } } }
```

Then instruct Claude Code: *"Before any deploy/push/secret-file read, call
`agentshield_gate`; if the decision is block, stop and explain."*

**Verify the hook works right now:**

```bash
echo '{"tool_name":"Read","tool_input":{"file_path":".env.production"},"session_id":"t"}' \
  | AGENTSHIELD_ROLE=engineering_intern python infra/scripts/claude_hook.py
```

Expected:

```json
{"decision": "deny", "hookSpecificOutput": {"hookEventName": "PreToolUse",
 "permissionDecisionReason": "AgentShield (pol_block_secret_read): Reading credential files is not permitted for this role."}}
```

---

## 8. Integrate Codex CLI

The exit-code contract: the hook exits **0** (allow, sandbox output printed)
or **1** (block, reason on stderr).

```bash
python infra/scripts/codex_hook.py deploy environment=production ; echo "exit=$?"
```

Expected as an intern:

```
BLOCKED by AgentShield [pol_intern_no_prod_deploy, …]: Production deployment is not available at this level.
exit=1
```

Wire into Codex (`~/.codex/config.toml`) as a command approval, or use it as
a plain shell wrapper anywhere.

---

## 9. Integrate Antigravity / Cursor / any MCP client

Any tool that speaks MCP gets the same gate. Register the server (same
command as above) and expose `agentshield_gate` to the agent with the
instruction: *"Before acting, ask; treat block as a hard stop."*

`agentshield_gate` arguments you'll actually use:

| Arg | Meaning |
|---|---|
| `role` | demo persona (`engineering_intern` … `devops`) |
| `mode` | `demo` (no key) or `live` (needs ingest `token`) |
| `prompt` | gate 1 — pre-flight the request |
| `tool` + `args` | gate 2 — check before executing |
| `token` | live-mode ingest bearer (identity resolved server-side) |

---

## 10. Integrate anything else (raw HTTP)

The universal hook — one URL, one decision contract:

```bash
curl -X POST http://localhost:8000/api/v1/playground/hook/agent \
  -H "Content-Type: application/json" \
  -d '{"mode":"demo","role":"engineer",
       "prompt":"Summarise config/database.yaml and fix the retry bug"}'
```

Decision contract:

| decision | caller must |
|---|---|
| `allow` | proceed (tool calls include the sandbox `result`) |
| `redact` | use the returned masked `prompt` |
| `review` | wait for the `approval_id` (poll `GET /api/v1/approvals/{id}`) |
| `block` | hard stop |

For production identity, register real tokens:

```env
INGEST_TOKENS=my-agent-token:emp_003,other-agent:emp_011
```

…and call with `mode: live` + `Authorization: Bearer my-agent-token`. The
body carries no identity; the server maps token → employee → role.

---

## 11. Test everything (with expected outputs)

### A. The full CI battery

```bash
python tasks.py check
```

Runs: ruff (lint) → mypy strict (domain/ports/governance/risk) → pytest (120
tests) → eslint → vitest → production web build. Expect the final line:
`all checks passed`.

### B. Contract suites (portability proof)

```bash
python tasks.py test-contract
```

The same suite runs against local adapters **and** AWS adapters via moto.
Skips fail the run — an AWS migration failing silently eight days early is
the failure mode this prevents.

### C. Safety canaries

```bash
python tasks.py check-secrets   # → "no raw secret values in persisted events or tasks"
```

This must stay zero forever: if a raw canary secret ever appears in storage,
Gate 1's redaction leaked.

### D. Detection quality (the hidden adversary)

```bash
python tasks.py evaluate
```

Scores the risk engine against ground truth (read only here): recall, false
positives split by decoy source, time-to-detection. Targets: recall ≥ 0.80,
FP ≤ 0.05.

### E. Manual end-to-end tour (10 minutes, no tools)

1. `python tasks.py dev` → open **:5173**
2. Office: press **▶ REAL TIME** → avatars work; click one → drawer shows
   live counters.
3. **SANDBOX**: role = Engineering Intern → **Deploy → production** → expect
   **BLOCK** with `pol_intern_no_prod_deploy`. Switch role to **DevOps**,
   repeat → **allow/review**.
4. **SANDBOX**: prompt containing `AKIAIOSFODNN7EXAMPLE` → Gate 1 returns
   **redact** and the masked prompt.
5. **LIVE FEED**: find those events; click a task → full trace.
6. **CONTROL → Policies**: toggle `pol_intern_no_prod_deploy` off, repeat
   step 3 → now only the manager-review policy remains (review, not block).
   Toggle it back on.
7. **APPROVALS**: as devops, request a prod deploy (review path), approve it
   in the UI, watch the Live Feed record `approval.decided`.

### F. Smoke the API surface directly

```bash
curl -s localhost:8000/healthz | head -c 200
curl -s "localhost:8000/api/v1/playground/context" | head -c 200
curl -s "localhost:8000/api/v1/metrics/summary?run_id=$(curl -s localhost:8000/api/v1/sim/runs | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["runs"][0]["id"])')" | head -c 200
```

---

## 12. Where the data lives / reset

| Path | What |
|---|---|
| `.data/agentshield.db` | Everything (single `items` table) |
| `.data/blobs/` | Raw prompts (the only place they exist) |
| `.data/dead-letter.jsonl` | Telemetry writes that failed after 3 tries |
| `.data/export/` | Dataset exports (`tasks.py export-dataset`) |

```bash
python tasks.py clean   # delete generated data; never touches source
```

---

## 13. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `No virtualenv at services/api/.venv` | Run `python tasks.py setup`. On macOS ensure a 3.11+ interpreter (see §2 note). |
| Web shows "Can't reach the AgentShield API" | API isn't running (`python tasks.py api`) or is on another port. |
| All `model.invoked` events show `fallback=true` | No `LLM_CLOUD_API_KEY`, Ollama down, or you're looking at `seed-history` data (always mock by design). Live-check after restarting the API with the key set. |
| `429` warnings in API logs | Free-tier limit hit; the breaker opens 60 s and Ollama/mock covers. Lower `SIM_LLM_INVOCATION_RATE` or `SIM_MAX_CONCURRENT_SESSIONS`. |
| Office empty / "No simulation yet" | Run `python tasks.py seed`. |
| Risk page shows everyone `low_confidence` | Run `python tasks.py seed-history` — baselines need ~14 sim-days. |
| Sandbox 401 | Use the `demo-<role>` prefix exactly: `Bearer demo-engineering_intern`. |
| Port already in use | Another process owns :8000/:5173 — `lsof -nP -iTCP:8000` to find it; never kill processes you didn't start. |
| `repro-check` differs | Known issue on some machines (task ids are wall-clock ULIDs); does not affect live operation or `evaluate` on the same machine. |
