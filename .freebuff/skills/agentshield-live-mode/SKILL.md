---
name: agentshield-live-mode
description: Use when changing /ingest endpoints, authentication, event schemas, or anything shared by real agents and the simulator. Guards the mode-parity guarantee and documents the integration contract.
alwaysApply: false
globs:
  - "services/api/agentshield/api/routes_ingest.py"
  - "packages/contracts/**"
  - "infra/scripts/reference_client.py"
---

# Live Mode: the same gates, over HTTP

Live Mode is where mode parity is either real or a marketing claim. `routes_ingest.py`
builds a `RequestContext` / `ActionContext` and calls `gate1.evaluate()` / `gate2.evaluate()`
— the **identical functions** the simulator calls. There is no parallel implementation to
drift. If you add a gate step, a policy field, or a decision path, both modes get it by
construction; never fork logic on `source`.

## Identity (the property that matters)

- The bearer token maps **server-side** (`Settings.ingest_tokens`, format
  `token:actor_id,...`) to a registered actor. The body carries no identity fields — an
  agent cannot assert its own role, so `ActorContext` is built from the employee record +
  counters (`_actor_context`).
- `INGEST_ENABLED=false` rejects everything; rate limit is 100 req/s/token (in-process
  deque; note it is per-worker).
- Live-mode tasks are real `Task` rows (`source=live`), so `/ingest/gate2` can look up
  session accounting from `TASK#<id>/META` and approval round-trips work unchanged.

## The three endpoints

| Endpoint | Body | Returns |
|---|---|---|
| `POST /ingest/gate1?run_id=` | `task_ref, task_type, complexity, repo, environment, prompt (≤100k), requested_model?` | `decision, reason, policy_ids, routed_model, est_cost_usd, prompt (redacted if findings), approval_id?, task_id` |
| `POST /ingest/gate2?run_id=` | `task_id, tool (one of 8), args, iteration` | `decision, reason, policy_ids, approval_id?` |
| `POST /ingest/events?run_id=` | `task_id, detail_type, payload` | `seq` (202) |

- A secret in the gate1 prompt comes back **redacted in the response**; the raw value
  never leaves the caller. `decision=block` means the model call should not happen.
- A gate2 `review` response carries `approval_id` — the caller polls
  `GET /approvals/{id}` or watches `approval.decided` on `/ws/stream`, then re-attempts.
- A gate2 `block` is data, not an exception: agents handle `blocked_by_policy` and adapt.
- `/ingest/events` validates `detail_type` against the **generated registry**
  (`domain/generated_events.EVENT_TYPES`), never a hardcoded count. Add events by editing
  `packages/contracts/events.schema.json` and running `python tasks.py contracts`.

## Testing an integration without touching prod

```bash
python tasks.py dev                                     # API on :8000
python infra/scripts/reference_client.py --run-id <run> # full round trip in ~60 lines
```

The reference client demonstrates the canonical sequence: gate1 (redaction demo) → gate2
allow → gate2 block (credential path) → gate2 review (deploy) → ingest a `task.completed`
event so it lands in the same Live Feed as sim traffic.

## Rules when changing shared core code

- `RequestContext`/`ActionContext` carry everything a gate needs and nothing about the
  caller; `policy_view()` excludes `source`. Adding a field means: model → `policy_view()`
  → DSL allowlist (if policy-addressable) → replay mirror in `telemetry/replay.py`.
- Both modes emit through the same `TelemetryEmitter`, so the Live Feed, office, risk
  engine and Policy Lab see one homogeneous stream.
- The contract test for parity lives in the backend suite; if you split a path, bring it
  back — the test exists to fail loudly.
