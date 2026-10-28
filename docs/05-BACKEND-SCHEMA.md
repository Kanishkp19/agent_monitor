# AgentShield — Backend Schema & API Contract

> Types referenced here are defined in `02-TRD.md §3`. The rationale for the single-table model is in `DESIGN.md §3.4`.

---

## 1. Database Choice

**One DynamoDB table, emulated locally in SQLite.**

Not Postgres, not an ORM. The reason is the portability goal: if the local store offers joins and ad-hoc queries, the code will use them, and the DynamoDB migration becomes a rewrite. By adopting the single-table access patterns from hour one, the AWS switch is a credentials change.

| | Local | AWS |
|---|---|---|
| Engine | SQLite (WAL, `aiosqlite`) | DynamoDB on-demand |
| Table | `items(pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl)` | `agentshield`, PK `pk` / SK `sk` |
| Index 1 | `idx_gsi1(gsi1pk, gsi1sk)` | GSI `gsi1`, projection ALL |
| Index 2 | `idx_gsi2(gsi2pk, gsi2sk)` | GSI `gsi2`, projection ALL |
| TTL | swept on tick | native TTL attribute |
| Permitted queries | `pk = ?` + (`sk LIKE ?||'%'` \| `sk BETWEEN ? AND ?`) | `Query` with `begins_with` / `between` |
| Forbidden | JOIN, GROUP BY, table scan, subquery | `Scan` |

Aggregations (spend by team, decision counts) are **maintained as counters on write**, never computed by scanning. See §4.

---

## 2. Entity-Relationship Map

```
                      ┌────────────────┐
                      │   SimRun       │  PK=RUN#<run_id>  SK=META
                      │   seed, speed  │
                      │   sim_ts, day  │
                      └────────┬───────┘
                               │ 1:many
       ┌───────────────┬───────┴────────┬──────────────┬──────────────┐
       ▼               ▼                ▼              ▼              ▼
 ┌───────────┐   ┌──────────┐    ┌───────────┐  ┌───────────┐  ┌──────────┐
 │ Employee  │   │  Event   │    │RiskProfile│  │ Incident  │  │ Counters │
 │ EMP#<id>  │   │EVT#<seq> │    │RISK#<emp> │  │ INC#<id>  │  │ CTR#...  │
 └─────┬─────┘   └────┬─────┘    └───────────┘  └───────────┘  └──────────┘
       │ 1:many       │
       ▼              │ (parallel, unreachable from risk/)
 ┌───────────┐        ▼
 │   Task    │   ┌──────────────┐
 │TASK#ts#id │   │ GroundTruth  │  SK=GT#<seq>   ◄── evaluation only
 └─────┬─────┘   └──────────────┘
       │ 1:many (under PK=TASK#<task_id>)
       ├──────────────┬───────────────┬────────────────┐
       ▼              ▼               ▼                ▼
 ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────┐
 │GateReq   │  │AgentAction │  │  Approval  │  │  Transcript  │
 │REQ#<id>  │  │ACT#<seq>   │  │APPR#<id>   │  │  TRANS#<n>   │
 └──────────┘  └────────────┘  └────────────┘  └──────────────┘

 Independent partitions:
 ┌──────────────┐  ┌──────────────┐  ┌────────────────┐
 │   Policy     │  │  Repository  │  │ PolicySimResult│
 │POLICY#<id>   │  │ REPO#<name>  │  │ PLAB#<id>      │
 │  SK=V#<ver>  │  │ SK=META|FILE#│  │ SK=META        │
 └──────────────┘  └──────────────┘  └────────────────┘
```

---

## 3. Key Design & Access Patterns

### 3.1 Item key table

| Entity | PK | SK | GSI1PK | GSI1SK | GSI2PK | GSI2SK |
|---|---|---|---|---|---|---|
| SimRun | `RUN#<run_id>` | `META` | `RUNS` | `<created_at>` | — | — |
| Employee | `RUN#<run_id>` | `EMP#<emp_id>` | `RUN#<run_id>#TEAM#<team>` | `EMP#<emp_id>` | — | — |
| Task | `RUN#<run_id>` | `TASK#<sim_ts:010d>#<task_id>` | `RUN#<run_id>#EMP#<emp_id>` | `TASK#<sim_ts:010d>` | `RUN#<run_id>#STATUS#<status>` | `<sim_ts:010d>` |
| Task detail | `TASK#<task_id>` | `META` | — | — | — | — |
| GateRequest | `TASK#<task_id>` | `REQ#<request_id>` | — | — | — | — |
| AgentAction | `TASK#<task_id>` | `ACT#<seq:04d>` | `RUN#<run_id>#TOOL#<tool>` | `<sim_ts:010d>` | — | — |
| Approval | `TASK#<task_id>` | `APPR#<approval_id>` | `RUN#<run_id>#APPR#<status>` | `<sim_ts:010d>` | `RUN#<run_id>#APPROVER#<emp_id>` | `<sim_ts:010d>` |
| Transcript chunk | `TASK#<task_id>` | `TRANS#<n:03d>` | — | — | — | — |
| Event | `RUN#<run_id>` | `EVT#<seq:012d>` | `RUN#<run_id>#TYPE#<detail_type>` | `<seq:012d>` | `RUN#<run_id>#EMP#<emp_id>#EVT` | `<seq:012d>` |
| **GroundTruth** | `RUN#<run_id>` | `GT#<seq:012d>` | — | — | — | — |
| RiskProfile | `RUN#<run_id>` | `RISK#<emp_id>` | `RUN#<run_id>#RISKRANK` | `<score:03d>#<emp_id>` | — | — |
| Incident | `RUN#<run_id>` | `INC#<incident_id>` | `RUN#<run_id>#INC#<status>` | `<opened_sim_ts:010d>` | — | — |
| Counter | `RUN#<run_id>` | `CTR#<dim>#<key>#<sim_date>` | — | — | — | — |
| Policy | `POLICY#<policy_id>` | `V#<version:04d>` | `POLICIES#<gate>` | `<priority:03d>#<policy_id>` | — | — |
| PolicyPointer | `POLICY#<policy_id>` | `CURRENT` | — | — | — | — |
| Repository | `REPO#<repo_name>` | `META` | — | — | — | — |
| RepoFile | `REPO#<repo_name>` | `FILE#<path>` | — | — | — | — |
| PolicyLabResult | `PLAB#<sim_id>` | `META` | — | — | — | — |
| SeqCounter | `SEQ#<run_id>` | `EVENT` | — | — | — | — |

Zero-padding is load-bearing: it makes lexicographic SK ordering equal numeric ordering, which is how DynamoDB range queries work.

### 3.2 Enumerated access patterns

Every read in the system must appear in this table. If yours is not here, add it plus its index **before** writing the code.

| # | Need | Query |
|---|---|---|
| A1 | Load a run | `get(RUN#<id>, META)` |
| A2 | List recent runs | `query(gsi1, pk=RUNS, desc, limit=20)` |
| A3 | All employees in a run | `query(pk=RUN#<id>, sk_prefix=EMP#)` |
| A4 | One employee | `get(RUN#<id>, EMP#<emp>)` |
| A5 | Employees on a team | `query(gsi1, pk=RUN#<id>#TEAM#<team>)` |
| A6 | Recent tasks in a run | `query(pk=RUN#<id>, sk_prefix=TASK#, desc, limit=50)` |
| A7 | Tasks for one employee | `query(gsi1, pk=RUN#<id>#EMP#<emp>, sk_prefix=TASK#, desc)` |
| A8 | Tasks by status | `query(gsi2, pk=RUN#<id>#STATUS#<status>, desc)` |
| A9 | Full task trace | `query(pk=TASK#<id>)` → META + REQ# + ACT# + APPR# + TRANS# in one call |
| A10 | Event page (Live Feed) | `query(pk=RUN#<id>, sk_between=(EVT#<from>, EVT#<to>))` |
| A11 | Events of one type | `query(gsi1, pk=RUN#<id>#TYPE#<type>, desc)` |
| A12 | Events for one employee | `query(gsi2, pk=RUN#<id>#EMP#<emp>#EVT, desc)` |
| A13 | Pending approvals | `query(gsi1, pk=RUN#<id>#APPR#pending, asc)` |
| A14 | Approvals for an approver | `query(gsi2, pk=RUN#<id>#APPROVER#<emp>, desc)` |
| A15 | Risk leaderboard | `query(gsi1, pk=RUN#<id>#RISKRANK, desc, limit=10)` |
| A16 | One risk profile | `get(RUN#<id>, RISK#<emp>)` |
| A17 | Open incidents | `query(gsi1, pk=RUN#<id>#INC#open, desc)` |
| A18 | Active policies for a gate | `query(gsi1, pk=POLICIES#<gate>)` then filter `enabled and not is_draft` in memory |
| A19 | Policy history | `query(pk=POLICY#<id>, sk_prefix=V#, desc)` |
| A20 | Current policy version | `get(POLICY#<id>, CURRENT)` |
| A21 | Daily counters for a dimension | `query(pk=RUN#<id>, sk_prefix=CTR#<dim>#)` |
| A22 | Repo file (sandbox read) | `get(REPO#<repo>, FILE#<path>)` |
| A23 | Replay window (Policy Lab) | A10 with a wide `sk_between` |
| A24 | Ground truth (evaluation only) | `query(pk=RUN#<id>, sk_prefix=GT#)` — **called only by `infra/scripts/evaluate.py`** |
| A25 | Actions by tool (analytics) | `query(gsi1, pk=RUN#<id>#TOOL#<tool>, desc)` |
| A26 | Autopilot job and report | `get(pk=AUTOPILOT#<job_id>, sk=JOB)`; events reuse A10 with `run_id=<job_id>` |

### 3.3 Label isolation, enforced in code

```python
class RiskScopedDocStore(DocStorePort):
    """Wrapper injected into risk/. Physically cannot read ground truth."""
    FORBIDDEN_PREFIXES = ("GT#",)

    async def query(self, *, pk, sk_prefix=None, **kw):
        if sk_prefix and sk_prefix.startswith(self.FORBIDDEN_PREFIXES):
            raise PermissionError("risk engine may not read ground truth")
        page = await self._inner.query(pk=pk, sk_prefix=sk_prefix, **kw)
        page.items = [i for i in page.items if not i.sk.startswith(self.FORBIDDEN_PREFIXES)]
        return page

    async def get(self, pk, sk):
        if sk.startswith(self.FORBIDDEN_PREFIXES):
            raise PermissionError("risk engine may not read ground truth")
        return await self._inner.get(pk, sk)
```

Plus `tests/test_label_isolation.py`, which deletes every `GT#` item and asserts feature vectors are byte-identical.

---

## 4. Counters (maintained on write)

Aggregations are never computed by scanning. On each relevant event the emitter issues an atomic increment:

| Counter SK | Incremented by | Fields |
|---|---|---|
| `CTR#emp#<emp_id>#<sim_date>` | every gate decision, model call | `requests, tokens, cost_usd, allowed, blocked, review, redacted` |
| `CTR#team#<team>#<sim_date>` | same | same |
| `CTR#model#<model_id>#<sim_date>` | `model.invoked` | `calls, tokens_in, tokens_out, cost_usd` |
| `CTR#tool#<tool>#<sim_date>` | `gate2.decision` | `attempted, allowed, blocked, review` |
| `CTR#run#<sim_date>` | everything | run-wide roll-up + `waste_usd` |
| `CTR#waste#<sim_date>` | blocked/denied/expired/retry-loop sessions | `waste_usd, sessions` |

DynamoDB: `UpdateItem` with `ADD`. SQLite: `INSERT … ON CONFLICT DO UPDATE SET body = json_patch(...)` inside a transaction. Both are exposed through `DocStorePort.update(patch={"$add": {...}})`.

**Definition of "potential waste":** total spend attributable to sessions that ended `blocked`, `denied`, `denied_timeout`, `failed`, or that triggered `pol_retry_loop_guard`. This is the number shown on the exec view, and it is defined here so the UI and the API never disagree.

---

## 5. Event Payload Schemas

Every event shares the envelope from `DESIGN.md §9.1`. The `detail.payload` shapes:

```typescript
// task.requested
{ task_id, employee_id, title, task_type, complexity, repo, environment, is_marquee }

// gate1.decision
{ task_id, request_id, decision, reason_code, matched_policies: PolicyMatch[],
  est_input_tokens, est_output_tokens, est_cost_usd, routed_model,
  findings: { detector, masked }[],        // masked only — never raw
  budget_remaining_usd, latency_ms }

// model.invoked
{ task_id, model_id, input_tokens, output_tokens, cost_usd,
  iteration, stop_reason, fallback }

// action.requested
{ task_id, action_id, tool, target_resource, environment,
  resource_sensitivity, args_digest, iteration }

// gate2.decision
{ task_id, action_id, tool, decision, reason_code,
  matched_policies: PolicyMatch[], target_resource, environment,
  repeat_count_5m, latency_ms }

// approval.requested
{ approval_id, task_id, action_id, requester_id, approver_role, approver_scope,
  reason, risk_at_request, cost_so_far_usd, expires_sim_ts }

// approval.decided
{ approval_id, task_id, status, approver_id, note, latency_sim_s }

// sandbox.executed
{ task_id, action_id, tool, ok, duration_ms, output_preview }   // ≤ 200 chars

// action.blocked
{ task_id, action_id, tool, target_resource, policy_id, message }

// task.completed
{ task_id, employee_id, status, tokens_in, tokens_out, cost_usd,
  actions_total, actions_blocked, duration_sim_s }

// budget.exceeded
{ employee_id, scope: "employee"|"team", budget_usd, spend_usd, sim_date }

// risk.updated
{ employee_id, score, static, behavioural, ml, confidence,
  top_factors: RiskFactor[], delta }

// incident.opened
{ incident_id, employee_id, detector, score, summary, evidence_count }

// sim.tick      { sim_ts, active_sessions, queued_tasks }
// sim.day.completed { sim_day, tasks, events, cost_usd, blocked, approvals, incidents }
```

Source of truth is `packages/contracts/events.schema.json`; the Pydantic and TypeScript versions are generated from it.

---

## 6. REST API Contract

Base: `/api/v1`. Content type `application/json`. Errors use the envelope in `02-TRD.md §6.1`.

### 6.1 Simulation

#### `POST /sim/runs`
Create and seed a run.

```typescript
// Request
{ seed?: number,                 // default SIM_SEED
  employee_count?: number,       // default 20, range 5..50
  speed?: 0|1|10|100,            // default 1
  scenario?: string,             // default "demo"
  start_sim_ts?: number }
// 201
{ data: { run_id, seed, employee_count, speed, sim_ts, scenario,
          employees: EmployeePublic[] } }
```
Errors: `400 validation_failed`.

#### `GET /sim/runs/{run_id}` → `200 { data: SimRun }` · `404 run_not_found`

#### `GET /sim/runs` → `200 { data: SimRunSummary[] }` (A2)

#### `POST /sim/runs/{run_id}/control`
```typescript
// Request
{ action: "start"|"pause"|"resume"|"reset"|"set_speed", speed?: 0|1|10|100 }
// 200
{ data: { run_id, status: "running"|"paused"|"reset", speed, sim_ts } }
```
Errors: `409 run_busy` if a 100× batch is mid-flight and the action is not `pause`.

#### `POST /sim/runs/{run_id}/advance`
Headless fast-forward. Streams progress frames over the WebSocket; returns the summary.
```typescript
// Request
{ sim_days?: number,             // default 1, max 30
  sim_hours?: number }           // alternative to sim_days
// 200
{ data: { sim_days_advanced, events_generated, tasks, tokens, cost_usd,
          blocked, approvals, incidents_opened, duration_wall_ms, final_sim_ts } }
```

#### `GET /sim/runs/{run_id}/state`
The office snapshot used for mount and rehydration.
```typescript
// 200
{ data: OfficeSnapshot }   // { run_id, seq, sim_ts, speed, avatars[], pending_approvals }
```

### 6.2 Employees

#### `GET /employees?run_id=&team=` → `200 { data: EmployeePublic[] }` (A3/A5)

#### `GET /employees/{emp_id}?run_id=`
```typescript
// 200
{ data: { employee: EmployeePublic,
          risk: RiskProfile,
          current_task: Task | null,
          recent_decisions: DecisionSummary[],     // last 10
          today: EmployeeDailyCounters,
          seven_day: { requests, tokens, cost_usd } } }
```
`scenario_profile` is absent from every response by construction (`EmployeePublic`).

### 6.3 Tasks

#### `GET /tasks?run_id=&employee_id=&status=&limit=&cursor=` → `200 { data: Task[], cursor }` (A6/A7/A8)

#### `GET /tasks/{task_id}` — full trace, one query (A9)
```typescript
// 200
{ data: { task: Task,
          gate1: GateRequest,
          actions: AgentAction[],
          approvals: Approval[],
          transcript: { role, content }[] } }
```

### 6.4 Events

#### `GET /events?run_id=&since_seq=&type=&employee_id=&limit=`
```typescript
// 200
{ data: EventEnvelope[], next_seq: number, has_more: boolean }
```
`limit` max 500. Used for initial Live Feed hydration and for WS gap recovery.

### 6.5 Approvals

#### `GET /approvals?run_id=&status=pending&approver_id=` (A13/A14)
```typescript
// 200
{ data: ApprovalCard[] }

interface ApprovalCard {
  approval: Approval
  requester: { id, name, role, team, risk_score, sprite_key }
  action: { tool, target_resource, environment, args_preview }
  context: { reason, policy_id, cost_so_far_usd, session_actions,
             requester_7d_rate_for_tool: number }   // "does this person normally do this"
}
```

#### `POST /approvals/{approval_id}/decide`
```typescript
// Request
{ decision: "approve_once"|"approve_session"|"deny", approver_id: string, note?: string }
// 200
{ data: { approval_id, status, task_status, decided_sim_ts } }
```
Errors: `409 approval_already_decided`, `404 not_found`.

### 6.6 Policies

#### `GET /policies?gate=&enabled=&include_drafts=` (A18)
```typescript
// 200
{ data: (Policy & { match_count_24h: number })[] }
```

#### `POST /policies`
Body: `PolicyCreate` (§7.2). `201 { data: Policy }` · `400 policy_invalid`.

#### `PATCH /policies/{policy_id}`
Creates version N+1 and repoints `CURRENT`. Body: partial `PolicyCreate`. `200 { data: Policy }`.

#### `POST /policies/{policy_id}/toggle` → `{ enabled: boolean }` → `200 { data: Policy }`

#### `GET /policies/{policy_id}/versions` → `200 { data: Policy[] }` (A19)

#### `POST /policies/validate`
Dry-run the DSL without saving.
```typescript
// Request  { when: object, gate: 1|2 }
// 200      { data: { valid: true, fields_used: string[] } }
// 400      { error: { code:"policy_invalid", field:"when.all[1].field", ... } }
```

### 6.7 Policy Lab

#### `POST /policy-lab/simulate`
```typescript
// Request
{ run_id: string,
  draft_policy: PolicyCreate,
  window_sim_hours?: number }        // default 24, max 168
// 200
{ data: {
    window: { from_seq, to_seq, from_sim_ts, to_sim_ts },
    decisions_replayed: number,
    requests_affected: number,
    requests_affected_pct: number,
    projected_spend_delta_usd: number,      // negative = savings
    projected_savings_pct: number,
    newly_blocked_previously_succeeded: number,   // false-positive proxy
    newly_blocked_previously_blocked: number,
    extra_approvals_per_day: number,
    affected_by_role: { role: string, count: number }[],
    sample_affected: { task_id, employee_id, tool_or_task_type, was, would_be }[]  // ≤ 10
  } }
```
Errors: `400 policy_invalid`, `404 run_not_found`.

#### `POST /policy-lab/promote` → `{ policy_lab_id }` → `201 { data: Policy }`

### 6.8 Risk & Incidents

#### `GET /risk/employees?run_id=&limit=` (A15) → `200 { data: RiskProfile[] }` (desc by score)

#### `GET /risk/employees/{emp_id}/explain?run_id=`
```typescript
// 200
{ data: { employee_id, score, static, behavioural, ml, confidence,
          top_factors: RiskFactor[],          // 3, plain-language explanations
          baseline: { feature: string, mean: number, std: number, current: number }[],
          recent_contributors: { event_seq, sim_ts, kind, detail }[] } }
```

#### `GET /incidents?run_id=&status=` (A17) → `200 { data: Incident[] }`

#### `POST /incidents/{incident_id}/acknowledge` → `200 { data: Incident }`

### 6.9 Metrics

#### `GET /metrics/summary?run_id=&scope=exec|security`
```typescript
// 200
{ data: {
    employees_enabled: number,
    requests_today: number,
    spend_today_usd: number,
    waste_prevented_usd: number,      // definition in §4
    blocked_actions: number,
    approvals_today: number,
    high_risk_sessions: number,
    open_incidents: number,
    spend_by_team: { team, usd }[],
    risk_by_team: { team, level: "low"|"medium"|"high", drivers: string[] }[],
    trend_7d: { sim_date, spend_usd, blocked, approvals }[]
  } }
```

#### `GET /metrics/spend?run_id=&group_by=team|employee|model&days=` (A21)
```typescript
// 200
{ data: { group_by, days, series: { key: string, usd: number,
          tokens: number, waste_usd: number }[] } }
```

### 6.10 Live Mode Ingest

All require `Authorization: Bearer <token>`; the token maps server-side to an `actor_id`. Rate limit 100 req/s per token → `429`.

#### `POST /ingest/gate1`
```typescript
// Request
{ task_ref: string,              // caller's own id, echoed back
  task_type: string, complexity: "trivial"|"standard"|"complex",
  repo: string, environment: "local"|"staging"|"production",
  prompt: string, requested_model?: string }
// 200
{ data: { decision: "allow"|"redact"|"review"|"block",
          reason: string, policy_ids: string[],
          routed_model: string, est_cost_usd: number,
          prompt: string,                 // redacted version when decision = redact
          approval_id?: string,           // when decision = review
          task_id: string } }             // use this on subsequent gate2 calls
```

#### `POST /ingest/gate2`
```typescript
// Request
{ task_id: string, tool: ToolName, args: object, iteration: number }
// 200
{ data: { decision: "allow"|"review"|"block", reason: string,
          policy_ids: string[], approval_id?: string } }
```
When `decision = review`, the caller polls `GET /approvals/{id}` or opens the WS and waits for `approval.decided`.

#### `POST /ingest/events`
```typescript
// Request
{ task_id: string, detail_type: string, payload: object }
// 202  { data: { seq: number } }
```
Rejects any `detail_type` outside the 14 known types, and any payload failing its schema.

### 6.11 Health

`GET /healthz` → `200 { status: "ok", env: "local"|"aws", adapters: {...} }`
`GET /readyz` → `200` when the docstore responds and policies are loaded, else `503`.

---

## 7. Validation (Pydantic)

### 7.1 Request models

```python
class CreateRunRequest(BaseModel):
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    employee_count: int = Field(20, ge=5, le=50)
    speed: Literal[0, 1, 10, 100] = 1
    scenario: str = Field("demo", pattern=r"^[a-z0-9_-]{1,32}$")
    start_sim_ts: int | None = None

class ControlRequest(BaseModel):
    action: Literal["start", "pause", "resume", "reset", "set_speed"]
    speed: Literal[0, 1, 10, 100] | None = None

    @model_validator(mode="after")
    def speed_required(self):
        if self.action == "set_speed" and self.speed is None:
            raise ValueError("speed is required when action is set_speed")
        return self

class AdvanceRequest(BaseModel):
    sim_days: int | None = Field(None, ge=1, le=30)
    sim_hours: int | None = Field(None, ge=1, le=720)

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.sim_days is None) == (self.sim_hours is None):
            raise ValueError("provide exactly one of sim_days or sim_hours")
        return self

class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve_once", "approve_session", "deny"]
    approver_id: str = Field(pattern=r"^emp_\d{3}$")
    note: str | None = Field(None, max_length=500)

class PolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    gate: Literal[1, 2]
    priority: int = Field(50, ge=0, le=999)
    effect: Literal["allow", "redact", "review", "block"]
    enabled: bool = True
    is_draft: bool = False
    when: dict
    approver: ApproverSpec | None = None
    ttl_sim_seconds: int = Field(300, ge=30, le=86_400)
    route_override: str | None = None
    message: str = Field(min_length=5, max_length=200)

    @model_validator(mode="after")
    def validate_dsl(self):
        errors = dsl.validate(self.when, gate=self.gate)   # returns [(path, msg), ...]
        if errors:
            path, msg = errors[0]
            raise PolicyInvalid(field=path, message=msg)
        if self.effect == "review" and self.approver is None:
            raise ValueError("approver is required when effect is review")
        if self.effect == "redact" and self.gate == 2:
            raise ValueError("redact is not a valid effect at gate 2")
        return self

class PolicyLabRequest(BaseModel):
    run_id: str
    draft_policy: PolicyCreate
    window_sim_hours: int = Field(24, ge=1, le=168)

class IngestGate1Request(BaseModel):
    task_ref: str = Field(max_length=128)
    task_type: str
    complexity: Literal["trivial", "standard", "complex"]
    repo: str = Field(pattern=r"^[a-z0-9._-]{1,64}$")
    environment: Literal["local", "staging", "production"]
    prompt: str = Field(max_length=100_000)
    requested_model: str | None = None

class IngestGate2Request(BaseModel):
    task_id: str
    tool: ToolName
    args: dict
    iteration: int = Field(ge=0, le=64)
```

### 7.2 Policy DSL validation

```python
FIELDS_GATE1 = {
    "actor.role", "actor.team", "actor.seniority", "actor.prod_access",
    "actor.risk_score", "actor.spend_today_usd", "actor.daily_budget_usd",
    "actor.sessions_today", "actor.is_low_confidence",
    "request.task_type", "request.complexity", "request.repo",
    "request.environment", "request.prompt_len", "request.requested_model",
    "request.est_cost_usd", "request.est_input_tokens", "request.routed_model",
    "request.findings_count", "request.finding_types", "request.off_hours",
}
FIELDS_GATE2 = {
    "actor.role", "actor.team", "actor.seniority", "actor.prod_access",
    "actor.risk_score", "actor.is_low_confidence",
    "action.tool", "action.environment", "action.target_resource",
    "action.resource_sensitivity", "action.repeat_count_5m",
    "action.iteration_index",
    "task.repo", "task.is_repo_in_scope", "task.is_secret_path",
    "task.is_protected_branch", "task.is_external_host",
    "task.cost_so_far_usd", "task.blocked_so_far", "task.elapsed_sim_s",
}
# Deliberately absent from both: "source". Policies must not differ between
# simulation and live mode. See DESIGN.md §4.

OPS = {"eq","neq","in","not_in","gt","gte","lt","lte","matches","contains","exists"}
COMBINATORS = {"all", "any", "none"}
MAX_DEPTH = 5
MAX_CONDITIONS = 25
```

`dsl.validate()` walks the tree and returns `[(json_path, message)]`. Unknown field, unknown op, depth overflow, or a type mismatch between op and value (e.g. `in` with a non-list) are all errors with the exact path.

---

## 8. Task State Machine

```
        queued
          │ scheduler picks up (concurrency cap)
          ▼
      requesting ──── gate1: block ────────────────────► blocked ──► (terminal)
          │      └─── gate1: review ──► awaiting_approval
          │                                  │ denied / expired
          │                                  ├──────────────► denied / denied_timeout
          │                                  │ approved
          │◄─────────────────────────────────┘
          │ gate1: allow | redact
          ▼
       working ──┬── gate2: review ──► awaiting_approval ──┬─► working (approved)
          │      │                                          └─► denied
          │      └── gate2: block ──► (tool result = refusal) ──► working
          │
          ├── agent returns no tool calls ─────────────────► completed
          ├── max iterations reached ──────────────────────► failed
          └── LLM error after fallback ────────────────────► failed
```

Legal transitions are asserted in `Task.transition_to()`; an illegal transition raises and is logged as a bug, never silently corrected.

## 9. Approval State Machine

```
   pending ──┬── approve_once ────► approved_once   ─► action executes, task resumes
             ├── approve_session ─► approved_session ─► same tuple auto-allowed for task
             ├── deny ───────────► denied            ─► task = denied
             └── TTL sweep ──────► expired           ─► task = denied_timeout
```

Terminal states are immutable; a second `decide` returns `409 approval_already_decided`.

---

## 10. Seed Data

`sim/seed.py`, invoked by `POST /sim/runs` and by `make seed`.

### 10.1 Organisation

```python
TEAMS = ["payments", "platform", "frontend", "data"]

REPOS = [
  {"name":"payments-api",  "team":"payments", "protected_branches":["main","release"],
   "has_secrets": True,  "environments":["local","staging","production"]},
  {"name":"payments-web",  "team":"payments", "protected_branches":["main"],
   "has_secrets": False, "environments":["local","staging","production"]},
  {"name":"platform-core", "team":"platform", "protected_branches":["main"],
   "has_secrets": True,  "environments":["local","staging","production"]},
  {"name":"infra-terraform","team":"platform","protected_branches":["main"],
   "has_secrets": True,  "environments":["staging","production"]},
  {"name":"web-app",       "team":"frontend", "protected_branches":["main"],
   "has_secrets": False, "environments":["local","staging"]},
  {"name":"data-pipeline", "team":"data",     "protected_branches":["main"],
   "has_secrets": True,  "environments":["local","staging","production"]},
]

SECRET_PATHS = [".env", ".env.production", ".env.staging",
                "secrets/db.yaml", "credentials.json", "keys/deploy.pem"]

EXTERNAL_ALLOWLIST = ["registry.npmjs.org", "pypi.org", "github.com",
                      "docs.python.org", "api.internal.acme"]
```

### 10.2 The 20 employees

| # | id | Name | Role | Team | Agent | Archetype | Manager | Profile |
|---|---|---|---|---|---|---|---|---|
| 1 | emp_001 | Vikram Nair | ceo | exec | internal | exec | — | normal |
| 2 | emp_002 | Sara Iyer | senior_manager | platform | claude_code | manager | emp_001 | normal |
| 3 | emp_003 | Ben Mathew | manager | payments | claude_code | manager | emp_002 | normal |
| 4 | emp_004 | Sarah Khan | senior_engineer | payments | claude_code | senior_engineer | emp_003 | normal |
| 5 | emp_005 | Arjun Menon | senior_engineer | platform | codex | senior_engineer | emp_002 | normal |
| 6 | emp_006 | Neha Gupta | senior_engineer | data | claude_code | senior_engineer | emp_002 | normal |
| 7 | emp_007 | Priya Sharma | engineer | payments | codex | engineer | emp_003 | normal |
| 8 | emp_008 | Aman Verma | engineer | payments | codex | engineer | emp_003 | normal |
| 9 | emp_009 | Rohit Das | engineer | platform | claude_code | engineer | emp_002 | normal |
| 10 | emp_010 | Meera Pillai | engineer | frontend | claude_code | engineer | emp_002 | normal |
| 11 | emp_011 | Kabir Shah | engineer | frontend | mcp | engineer | emp_002 | normal |
| 12 | emp_012 | Ananya Roy | engineer | data | codex | engineer | emp_002 | normal |
| 13 | emp_013 | Rahul Sharma | engineering_intern | payments | codex | intern | emp_003 | normal |
| 14 | emp_014 | Ishaan Bose | engineering_intern | payments | codex | intern | emp_003 | **sloppy** |
| 15 | emp_015 | Tara Nair | engineering_intern | frontend | claude_code | intern | emp_002 | normal |
| 16 | emp_016 | Dev Malhotra | engineering_intern | data | codex | intern | emp_002 | normal |
| 17 | emp_017 | Nikhil Rao | engineer | platform | internal | engineer | emp_002 | **adversarial** |
| 18 | emp_018 | Zoya Ahmed | engineering_intern | platform | claude_code | intern | emp_002 | normal |
| 19 | emp_019 | Mark Dsouza | devops | platform | internal | devops | emp_002 | normal |
| 20 | emp_020 | Lakshmi Iyer | engineer | data | claude_code | engineer | emp_002 | normal |

`emp_017` is deliberately an unremarkable mid-level platform engineer — not an intern, not a senior — so the detector cannot win by role alone. `emp_014` is the sloppy decoy: high mistake rate, retry loops, budget burn, zero malice.

### 10.3 The 12 seeded policies

| id | Gate | Effect | Priority | Condition (summary) |
|---|---|---|---|---|
| `pol_block_secret_read` | 2 | block | 200 | `task.is_secret_path = true` AND `actor.role not_in [devops]` |
| `pol_devops_secret_scope` | 2 | review | 190 | `task.is_secret_path = true` AND `actor.role = devops` AND `task.is_repo_in_scope = false` |
| `pol_prod_deploy_requires_manager` | 2 | review | 180 | `action.tool = deploy` AND `action.environment = production` AND `actor.role not_in [devops]` |
| `pol_intern_no_prod_deploy` | 2 | block | 185 | `action.tool = deploy` AND `action.environment = production` AND `actor.role = engineering_intern` |
| `pol_external_fetch_allowlist` | 2 | block | 170 | `action.tool = external_fetch` AND `task.is_external_host = true` |
| `pol_protected_branch_push` | 2 | review | 150 | `action.tool = git_push` AND `task.is_protected_branch = true` |
| `pol_out_of_scope_repo` | 2 | review | 140 | `task.is_repo_in_scope = false` |
| `pol_retry_loop_guard` | 2 | block | 160 | `action.repeat_count_5m >= 3` |
| `pol_prod_api_high_risk` | 2 | review | 130 | `action.tool = call_api` AND `action.environment = production` AND `actor.risk_score > 60` |
| `pol_redact_secrets` | 1 | redact | 200 | `request.findings_count > 0` |
| `pol_intern_model_downgrade` | 1 | allow | 90 | `actor.role = engineering_intern` AND `request.complexity = trivial` → `route_override = trivial` |
| `pol_high_risk_review` | 1 | review | 120 | `actor.risk_score > 80` AND `request.environment = production` |

These twelve are exactly what the demo exercises. The Policy Lab's showcase draft is a 13th:

```json
{
  "name": "Interns may not use advanced models for low-complexity tasks",
  "gate": 1, "effect": "allow", "priority": 95, "is_draft": true,
  "route_override": "trivial",
  "when": { "all": [
    { "field": "actor.role", "op": "eq", "value": "engineering_intern" },
    { "field": "request.complexity", "op": "in", "value": ["trivial", "standard"] },
    { "field": "request.routed_model", "op": "contains", "value": "sonnet" }
  ]},
  "message": "Routed to the standard model for low-complexity work."
}
```

### 10.4 Seed script

```bash
make seed            # creates run, 20 employees, 6 repos + files, 12 policies
make seed-history    # additionally advances 14 sim-days so baselines exist
```

`make seed-history` matters: without it, every employee is `low_confidence` and the risk engine has nothing to compare against. The demo should always run after it.
