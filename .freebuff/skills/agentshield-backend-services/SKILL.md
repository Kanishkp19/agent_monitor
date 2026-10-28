---
name: agentshield-backend-services
description: Use when implementing backend features in services/api — adding routes, governance steps, risk signals, telemetry, ports/adapters, or persistence reads. Maps every module by its real symbols, the single-table key layout, the REST surface, and the placement playbook for each kind of change.
alwaysApply: false
globs:
  - "services/api/agentshield/**/*.py"
---

# Backend services map (services/api/agentshield)

FastAPI 0.115 + Pydantic v2 + aiosqlite, ports-and-adapters. `container.py` is the only
composition root; everything else depends on the 8 ports in `ports/`. Read
`docs/graph/GRAPH.md` once for the full picture — this skill is the working map.

## Module map with the real symbols

| Path | What lives there (key symbols) |
|---|---|
| `main.py` | FastAPI app, lifespan, CORS, WS mount |
| `config.py` | `Settings` (pydantic-settings) — the ONLY file that reads `AGENTSHIELD_ENV` |
| `container.py` | `Container` — the ONLY file that imports `agentshield.adapters` or branches on env |
| `deps.py` | `Services`, `get_services` — FastAPI DI; routes never build adapters themselves |
| `domain/` | `enums.py` (Decision, TaskStatus, …), `models.py` (Employee, Task, GateRequest, DecisionResult, RequestContext, ActionContext, Approval, Policy…), `events.py` (EventEnvelope), `generated_events.py` (generated — never hand-edit), `errors.py` (NotFound…) |
| `ports/` | `llm docstore blobstore eventbus metrics queue secrets clock` — Protocols, zero vendor imports |
| `adapters/local/` | `SqliteDocStore` (single `items` table), `FsBlobStore`, `MemoryBus`, `AsyncioQueue`, `StdoutMetrics`, `DotenvSecrets`, `MockLLMAdapter`, `OllamaAdapter`, `OpenAICompatAdapter` (free cloud: Groq/Gemini/OpenRouter), `HybridAdapter` (cloud → ollama → mock chain, breaker + rate limiter) |
| `adapters/aws/` | Dynamo/S3/EventBridge/SQS/CloudWatch-EMF/SecretsManager/Bedrock mirrors (boto3 sync on `asyncio.to_thread`) |
| `governance/` | `gate1.py` (`Gate1.evaluate` — 10 named steps, pure, fails closed), `gate2.py` (`Gate2.evaluate`, no redact), `policy_engine.py` (cache invalidated on write only), `dsl.py` (`evaluate`, `validate`, `validate_or_raise`, `fields_used`), `precedence.py` (fixed `block > review > redact > allow`), `redaction.py` (`scan`, `<<REDACTED:type:sha256[:4]>>`), `budget.py` (`BudgetGuard`), `approvals.py` (`sweep_expired` on sim time) |
| `agent/` | `runner.py` (`AgentRunner` — ≤8-iteration tool loop; blocks are tool results, not exceptions), `router.py` (`PRICE_TABLE` — the single cost source; `price_for` never raises), `tools.py`/`prompts.py` (8 closed tool schemas; `task_type=` marker in prompt) |
| `sandbox/` | `executor.py`, `vfs.py` — fully simulated; secret files exist so blocking them is a real event |
| `sim/` | `engine.py` (tick loop, speeds 1/10/100, `advance()` forces MockLLM), `persona.py` (`seeded_rng(seed, *parts)`, `LADDER`), `task_generator.py` (diurnal curve), `scenarios.py` (ONLY ground-truth producer), `seed.py`/`seed_data.py` (20 employees, 13 policies), `clock.py` (`SimClock`), `office_map.py`, `snapshot.py` |
| `risk/` | `engine.py` (`RiskEngine.observe`, `score_session` at `task.completed`), `scoring.py` (0.35 static + 0.40 behavioural + 0.25 ml; `explain()` is the single wording source), `features.py` (12-feature vector), `baseline.py` (Welford per-employee; <20 sessions ⇒ `low_confidence`), `isolation.py` (IsolationForest, refuses <50 sessions), `incidents.py` (≥70 twice consecutively or static-critical; merge 24 sim-h), `scoped_store.py` (`RiskScopedDocStore`, `LabelLeakError`) |
| `telemetry/` | `emitter.py` (`TelemetryEmitter.emit` — THE choke point; atomic `seq` via `$add`; 3 write retries → `.data/dead-letter.jsonl` + `degraded`), `counters.py` (six counter families, `$add` on write) |
| `api/` | `routes_sim.py`, `routes_core.py` (employees/tasks/events/approvals), `routes_policies.py` (+validate/fields), `routes_risk.py` (leaderboard, explain, incidents), `routes_metrics.py` (summary, spend; team risk = **max** of members), `routes_ingest.py` (LIVE entry), `ws.py` (seq-cursor replay; gap >500 ⇒ resnapshot; 15 s heartbeat), `schemas.py` (`ok()` envelope), `errors.py` |

## REST surface (prefix `/api/v1` unless noted)

- Sim: `POST /runs` · `GET /runs[/{id}]` · `POST /runs/{id}/control` · `POST /runs/{id}/advance {sim_days}` · `GET /runs/{id}/state` (rehydration snapshot incl. `seq` cursor)
- Core: `GET /employees[?team=]`, `GET /employees/{id}` (risk + current task + recent decisions), `/tasks` (`/tasks/{id}` = full trace, one query), `/events`, `/approvals` (+ decide)
- Policies: `GET/POST /policies`, `PATCH /{id}` (append-only new version), `POST /{id}/toggle`, `GET /{id}/versions`, `POST /policies/validate`, `GET /policies/fields`
- Risk: `GET /risk/employees`, `GET /risk/employees/{id}/explain`, `GET /risk/weights`, `GET /incidents`, `POST /incidents/{id}/acknowledge`
- Metrics: `GET /summary`, `GET /spend`
- Live: `POST /ingest/gate1|gate2|events` (Bearer token → actor server-side)
- Playground (no sign-in): `GET /playground/context`, `POST /playground/gate1|gate2|tool|tasks/create`,
  `POST /playground/hook/agent` — `Bearer demo-<role>` maps to a seeded persona; the same
  gates run; tool calls execute in the sandbox on allow. Integration point for Claude Code
  (hooks), Codex (exit-code), and any MCP client via `agentshield_gate`.
- `GET /healthz` (names each adapter), `GET /readyz`; WS `GET /ws/stream?since_seq=`

## Single-table key layout (`RUN#<id>` partition unless stated)

`META · EMP#… · TASK#<ts>#… · EVT#<seq:012d> · RISK#… · SESSION#… · BASELINE#… · ARCHBASE#… · INC#… · CTR#… · GT#<seq>` ·
`TASK#<id>` + `META/REQ#/ACT#<seq>/APPR#…` (full trace in one query) ·
`POLICY#<id>` + `V#…`/`CURRENT`, GSI `POLICIES#<gate>` · `APPRIDX#<id>`, GSI `RUN#<id>#APPR#<status>` · `REPO#<name>` + `FILE#<path>` · `SEQ#<run>` atomic counter.
Zero-padding in sort keys is load-bearing (lexicographic == numeric). Blobs: `raw/{task_id}/prompt.json` is the ONLY place a raw prompt exists.

## Placement playbook (where a change goes)

- New rule/behaviour switch → a `Policy` row (DSL). Not new Python branching.
- New read path → check `docs/05-BACKEND-SCHEMA.md` §3.2 access patterns first; add the
  pattern + index there BEFORE writing the store method.
- New external dependency → extend/add a port + two adapters + contract test.
- New risk signal → `risk/features.py` feature + weight in `risk/scoring.py` + wording in
  `explain()` (one wording source, no ad-hoc strings elsewhere).
- New event type → `packages/contracts/events.schema.json`, then `python tasks.py contracts`
  (both generated files are committed together).
- New request context field → model → `policy_view()` → DSL allowlist (if
  policy-addressable) → replay mirror in `telemetry/replay.py`, in the same change.
- Every event, always → `TelemetryEmitter.emit()`. Never construct an `EventEnvelope`
  elsewhere; never publish to the bus directly from domain code.
