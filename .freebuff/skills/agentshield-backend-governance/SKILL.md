---
name: agentshield-backend-governance
description: Use when changing the two gates, policies/DSL, approvals, budget, redaction, agent runner, or risk engine. Carries the fail-closed, precedence, label-isolation and determinism rules plus the data-flow order every change must preserve.
alwaysApply: false
globs:
  - "services/api/agentshield/governance/**/*.py"
  - "services/api/agentshield/risk/**/*.py"
  - "services/api/agentshield/agent/**/*.py"
  - "services/api/agentshield/telemetry/**/*.py"
---

# Governance, risk & agent data flow — rules that must not bend

These are asserted by `tests/test_architecture.py` and the contract suites, but know them
before you write: a broken invariant fails CI *after* you've built on sand.

## The flow (order is load-bearing)

```
Gate1.evaluate(RequestContext)          # scan → budget → policies → precedence → resolve
  ALLOW  → AgentRunner.run(task, actor)          # ≤8 iterations
             LLMPort.complete                    # MockLLM script | Ollama | Bedrock
             every tool call → Gate2.evaluate(ActionContext)
                 BLOCK  → tool result {"error":"blocked_by_policy", …}   # model continues
                 REVIEW → ApprovalEngine.request → decide/expire (sim time)
                 ALLOW  → Sandbox.execute (seeded, never real I/O)
  REDACT → prompt masked; raw → blob store raw/{task_id}/prompt.json ONLY
  BLOCK  → task terminal; cost counted as waste
every step → TelemetryEmitter.emit() → docstore EVT#seq → bus → WS → metrics → RiskEngine
task.completed → RiskEngine.score_session → RiskProfile → incident?
```

Gate 1 scans the prompt **before any other step touches the text** so no downstream step
can persist or log a raw value. Budget is checked before the model call, not after.

## Non-negotiables

- **Fails closed.** Any gate exception ⇒ `DecisionResult(BLOCK, reason_code="gate_error")`.
  New gate steps must keep the failure path blocking. A governance layer that fails open
  produces false evidence it was working.
- **Gates are pure.** Context in → `DecisionResult` out. No persistence, no emission —
  the caller (sim engine, `/ingest/*`) persists and emits. This is what makes Simulation
  and Live mode structurally identical.
- **Precedence fixed**: `block > review > redact > allow`; priority is attribution only;
  ties break on policy id. Gate 2 has no redact (`PolicyCreate` enforces).
- **Label isolation (I4).** `risk/` never imports `sim/persona|scenarios|seed`, never
  names `ScenarioProfile`, and `RiskScopedDocStore` raises `LabelLeakError` on `GT#`
  keys. Only `infra/scripts/evaluate.py` reads ground truth. No exceptions "just this
  once" — the hidden-actor exercise is the product's honesty test.
- **One choke point.** All events via `TelemetryEmitter.emit()`; nothing else builds an
  `EventEnvelope`. Ordering by `seq` (atomic `$add`), never wall time. Durability first:
  3 write attempts → `.data/dead-letter.jsonl` + `degraded` flag; fan-out can never fail
  the emit.
- **Blocks are tool results, not exceptions** — the model's reaction to a refusal is
  adversarial telemetry; killing the loop would hide it. Repeat-digest window = 5 sim-min.
- **Determinism.** Every sim draw via `seeded_rng(seed, *parts)`; never module-level
  `random`, wall time, or set-iteration order in anything scored/hashed. `advance()`
  forces MockLLM. Expiry/sweeps read `clock.sim_ts`, never wall time.
- **Raw secrets stop at Gate 1**; findings carry `{detector, masked}` only. `python
  tasks.py check-secrets` must always be zero.
- **Approvals**: terminal states immutable (second decide ⇒ 409); `approve_session`
  grants `tool|resource|env` for that task only; TTL expiry on sim time ⇒ `denied_timeout`.

## When you add a gate step, policy field, or risk feature

1. Gate step: keep it pure, wrap-or-propagate so failure still blocks, and remember both
   modes get it by construction (never fork on `source`).
2. New `RequestContext`/`ActionContext` field: model → `policy_view()` (excludes
   `source`) → DSL per-gate allowlist (`FIELDS_GATE1`/`FIELDS_GATE2` in `dsl.py` — add
   only if policies should address it) → replay mirror in `telemetry/replay.py`
   (`_policy_view`), all in the same change, or the Policy Lab silently goes stale.
3. New risk signal: `risk/features.py` feature → weight in `risk/scoring.py` → wording in
   `risk/scoring.explain()` (single source of plain-language explanations). Baselines are
   Welford per-employee; < 20 sessions ⇒ `low_confidence` — don't "fix" that, seed more
   history (`python tasks.py seed-history`).
4. Cost: every dollar figure comes from `router.PRICE_TABLE` — never inline a price.

## Verify before finishing

```bash
python tasks.py typecheck        # mypy strict on domain/ports/governance/risk
python tasks.py test             # unit + contract + e2e + architecture guard
python tasks.py check-secrets    # must be zero
python tasks.py repro-check      # after sim/agent/sandbox/telemetry changes
```
