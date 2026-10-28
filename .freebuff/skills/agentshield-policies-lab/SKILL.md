---
name: agentshield-policies-lab
description: Use when touching policies, the DSL, the policy editor UI, or the Policy Lab replay. Covers the condition grammar, per-gate field allowlists, versioning rules, and what every replay number means.
alwaysApply: false
globs:
  - "services/api/agentshield/governance/**"
  - "services/api/agentshield/api/routes_policies.py"
  - "apps/web/src/routes/control/policies.tsx"
  - "apps/web/src/routes/control/policy-lab.tsx"
---

# Policies and the Policy Lab

## The DSL (governance/dsl.py)

Condition trees: combinators `all` / `any` / `none` over leaf tests
`{"field", "op", "value"}`. Operators: `eq neq in not_in gt gte lt lte matches contains
exists`. Constraints: `MAX_DEPTH 5`, `MAX_CONDITIONS 25`, regex patterns capped at 200
chars (validated by compiling). An empty condition matches everything (unconditional
policy).

**Field allowlists are per gate and closed.** Gate 1 fields are `actor.*` and
`request.*`; Gate 2 adds `action.*` and `task.*` (see `FIELDS_GATE1`/`FIELDS_GATE2`).
`source` (sim vs live) is deliberately absent from both — a policy that could read the
mode would break mode parity. An unknown field is a validation error carrying the JSON
path plus a "Did you mean X?" suggestion (`difflib`), never a silent no-match — a policy
that silently never fires is a control the operator believes they have.

Validation entry points: `dsl.validate(node, gate) -> [(json_path, message)]` (never
raises), `dsl.validate_or_raise` (raises `PolicyInvalid` with `field` — that's what the
editor underlines), `dsl.fields_used` (drives editor autocomplete via `POST
/policies/validate` and `GET /policies/fields`).

## Semantics you must preserve

- **Precedence is fixed**: `block > review > redact > allow` (`governance/precedence.py`).
  Higher priority wins attribution only. A draft `allow` can never override a live
  `block` (Policy Lab uses `precedence.strongest`).
- **Gate 2 has no redact** — `PolicyCreate` rejects it (and rejects `review` without an
  approver). Redact at gate 2 degrades to review if it ever appears.
- **Policies are append-only**: PATCH creates version N+1; `V#` rows stay; `CURRENT`
  repoints. The Policy Lab replays against the version that was live at the time.
- **Cache invalidated on write only** (`PolicyEngine.invalidate`); hot-path lookups use
  `cached_policy` (no IO). Evaluation is a linear scan — do not introduce a rules engine.
- **Route overrides**: an `allow` policy with `route_override` downgrades the model for
  matched requests; `sim/engine` recomputes `est_cost_usd` from `PRICE_TABLE` so savings
  are real, not notional.

## The seeded twelve (sim/seed_data.py) — know the showcase ones

- `pol_block_secret_read` (gate 2, block): secret path + role ≠ devops.
- `pol_intern_no_prod_deploy` (block) vs `pol_prod_deploy_requires_manager` (review,
  approver manager/team, TTL 300).
- `pol_retry_loop_guard` (block): `action.repeat_count_5m >= 3`.
- `pol_intern_model_downgrade` (allow + route_override trivial) — the cost story.
- `SHOWCASE_DRAFT` (`pol_draft_intern_downgrade`, is_draft=true) — never enabled; widening
  the downgrade to `trivial|standard` yields the demo's "21% projected savings,
  3 legitimate blocks".

## Policy Lab replay (telemetry/replay.py)

Replays a draft against recorded gate decisions. It works only because every decision
(`GateRequest` / `AgentAction`) stores a full `context_snapshot` (~2 KB, deliberate —
decision D8). `_policy_view()` rebuilds the flat field map from a snapshot; if
`RequestContext.policy_view()` / `ActionContext.policy_view()` change, update the replay
mirror in the same change or the Lab silently evaluates stale fields.

Numbers and their meaning:
- `requests_affected(_pct)` — draft matches at all.
- `newly_blocked_previously_succeeded` — **the false-positive proxy**; work that completed
  and the draft would stop. High = the rule will generate tickets.
- `newly_blocked_previously_blocked` — redundant coverage.
- `extra_approvals_per_day` — human cost of the draft.
- `projected_spend_delta_usd` / `projected_savings_pct` — from `PRICE_TABLE` via
  `_route_saving` (route drafts) or blocked-request cost (block drafts).

## Editor UX contract

`/policies/validate` is called debounced while typing; it returns `valid` and
`fields_used` so the autocomplete can only offer fields the gate accepts. Error toasts
should show the server's `field` path (the `ApiError.field` from `lib/api.ts`).
