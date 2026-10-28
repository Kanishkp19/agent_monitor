---
name: agentshield-core-invariants
description: Use when working in services/api (or packages/contracts). Lists AgentShield's hard architectural invariants, what is deliberately NOT abstracted, and the exact pre-finish verification commands. Load before editing governance, risk, sim, telemetry, or adapters.
alwaysApply: false
globs:
  - "services/api/**/*.py"
  - "packages/contracts/**"
---

# AgentShield core invariants

AgentShield is a governance control plane: two gates, an append-only policy engine, a
label-isolated risk engine, and a single telemetry choke point. The invariants below are
asserted by `tests/test_architecture.py` and the contract suites — a change that breaks
one will fail `python tasks.py test`, but know them *before* you write code.

## The 12 invariants

1. **Ports, not vendors.** `boto3/aiobotocore` only in `adapters/aws/`; `sqlite3/aiosqlite/httpx`
   only in `adapters/local/`. Domain code imports `agentshield.ports`. (ruff banned-api + AST guard)
2. **One composition root.** Only `container.py` imports `agentshield.adapters`. Everything
   else depends on ports. `sim/` needing a deterministic LLM asks `container.deterministic_llm()`.
3. **Environment is invisible.** Only `config.py` *reads* `AGENTSHIELD_ENV` (loads it into
   typed settings); only `container.py` *branches* on `settings.env`. No other file may
   compare it. The migration story depends on this.
4. **Label isolation.** `risk/` may not import `sim/persona.py`, `sim/scenarios.py`,
   `sim/seed.py` nor name `ScenarioProfile`. At runtime `RiskScopedDocStore` raises
   `LabelLeakError` on any `GT#` key. Only `infra/scripts/evaluate.py` reads ground truth.
   Never "just this once" wire a label into a feature.
5. **One telemetry choke point.** Every event goes through `telemetry/emitter.py::emit()`.
   Nothing else constructs or writes `EventEnvelope`. Gate code is pure — callers persist
   and emit.
6. **Precedence is fixed**: `block > review > redact > allow`. Never make it configurable.
   Priority decides *attribution only*. Gate 2 has no redact (you cannot partially read a
   secret file) — `PolicyCreate` enforces this.
7. **Fail closed.** Any exception inside a gate returns `BLOCK` with `reason_code=gate_error`.
   If you add a step to a gate, wrap-or-propagate so the failure path still blocks.
8. **Ordering is `seq`, never wall time.** `seq` is a monotonic per-run counter taken via an
   atomic `$add`. `sim_ts` is display only. Approvals expiry, sweeps and schedules read
   `clock.sim_ts` (a wall-time sweep deadlocks fast-forwards).
9. **Raw secrets stop at Gate 1.** Findings in events carry `{detector, masked}` only.
   The raw prompt goes to blob store `raw/{task_id}/prompt.json` and nowhere else.
   `python tasks.py check-secrets` must always report zero canary hits.
10. **Determinism.** Every sim draw uses `seeded_rng(seed, *parts)`; never module-level
    `random`, never wall time, never `set`/dict iteration order in anything scored or
    hashed. `advance()` forces `MockLLM` regardless of `LLM_PROVIDER`.
11. **Adopt the model, abstract the transport.** DocStore is DynamoDB-shaped (single table,
    key conditions only, zero-padded sort keys, `$add` aggregates — no joins, no scans,
    no OFFSET). `LLMResult` mirrors Bedrock Converse. If a new read doesn't fit
    `put/get/query(key-condition)/update/delete`, add it to `docs/05-BACKEND-SCHEMA.md`
    §3.2 with an index BEFORE writing the code.
12. **Blocks are tool results, not exceptions.** A Gate 2 refusal returns
    `{"error":"blocked_by_policy", ...}` to the model loop so its reaction stays observable.

## When adding a feature, place it by layer

- New rule? A `Policy` row (DSL, per-gate field allowlist — `source` is absent on purpose),
  not new Python branching.
- New external dependency? A port (or extend one) + two adapters + contract test.
- New read path? An access pattern (pk/sk + index) — then a method on the relevant store.
- New behaviour signal? A `risk/features.py` feature + weight in `risk/scoring.py` +
  explanation in `explain()` (the single wording source).
- New event? `packages/contracts/events.schema.json`, then `python tasks.py contracts`
  (both generated files are committed).

## Verify before finishing (run from repo root)

```bash
python tasks.py check            # lint + mypy(strict on domain/ports/governance/risk) + tests + web build
python tasks.py test-contract    # contract suites run against BOTH adapter sets; skips fail
python tasks.py check-secrets    # canary scan must be zero
python tasks.py repro-check      # same seed => identical event hash
```

Frontend-only changes still need `python tasks.py lint-web && python tasks.py test-web &&
python tasks.py build`. If you touched `events.schema.json` or either generated file, run
`python tasks.py contracts` and commit both outputs together.
