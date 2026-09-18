# AgentShield — System Design & Architecture

> This is the document to read when you want to know *why*. `02-TRD.md` tells you what to install; this tells you what shape the system is and which invariants must never break.

---

## 1. Design Goals, Ranked

When two goals conflict, the higher one wins. This ordering is the tie-breaker for every decision in the build.

1. **Mode parity.** Simulation and Live Mode must be indistinguishable to the governance core. If a code path exists for one and not the other, the design is wrong.
2. **Portability.** Local and AWS are two adapter sets behind one set of ports. Domain code must not know which is running.
3. **Determinism.** Given a seed and `LLM_PROVIDER=mock`, the entire simulation is reproducible. Without this you cannot debug, cannot evaluate a detector, and cannot demo reliably.
4. **Evidence integrity.** Ground-truth labels are physically unreachable from the detector's code path. An evaluation you can fool is not an evaluation.
5. **Explainability.** Every decision and every risk score carries its reasons. A control plane that cannot say why is a black box replacing a black box.
6. **Demo legibility.** The system must be understandable by a stranger in ninety seconds. This is a real goal, not decoration — it is why the office exists.

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│ BROWSER — apps/web (Vite + React 19)                                       │
│                                                                            │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌────────────────┐                │
│  │  OFFICE  │ │   LIVE   │ │ APPROVALS │ │ CONTROL CENTER │                │
│  │ (Phaser) │ │   FEED   │ │           │ │  + POLICY LAB  │                │
│  └────┬─────┘ └────┬─────┘ └─────┬─────┘ └───────┬────────┘                │
│       └────────────┴─────────────┴───────────────┘                         │
│                          │                                                 │
│              Zustand stores (simStore · telemetryStore · uiStore)          │
│                    ▲                              ▲                        │
│                    │ WS frames                    │ TanStack Query         │
└────────────────────┼──────────────────────────────┼────────────────────────┘
                     │ /ws/stream                   │ /api/v1/*
┌────────────────────┼──────────────────────────────┼────────────────────────┐
│ services/api — FastAPI (one process, asyncio)     │                        │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ ENTRY POINTS                                                         │  │
│  │   SimulationEngine  ──┐                      ┌── /ingest/gate1       │  │
│  │   (internal driver)   │                      │   /ingest/gate2       │  │
│  │                       │                      │   /ingest/events      │  │
│  │                       ▼                      ▼   (Live Mode)         │  │
│  └───────────────────────┬──────────────────────┬──────────────────────┘  │
│                          └──────────┬───────────┘                          │
│                                     ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ GOVERNANCE CORE  ◄── identical for both entry points                  │  │
│  │                                                                       │  │
│  │   gate1.evaluate(RequestContext) ──► Decision                        │  │
│  │        ├─ policy_engine.match()      (JSON DSL, precedence)          │  │
│  │        ├─ redaction.scan()           (7 secret detectors)            │  │
│  │        ├─ budget.check()                                             │  │
│  │        └─ risk.current(actor)        (read-only)                     │  │
│  │                                                                       │  │
│  │   gate2.evaluate(ActionContext)  ──► Decision                        │  │
│  │        ├─ policy_engine.match()                                      │  │
│  │        ├─ scope.check(repo, env, tool)                               │  │
│  │        └─ risk.current(actor)                                        │  │
│  │                                                                       │  │
│  │   approvals.request() / decide() / expire()                          │  │
│  └───────────────────────┬──────────────────────────────────────────────┘  │
│                          │                                                 │
│         ┌────────────────┼────────────────┐                                │
│         ▼                ▼                ▼                                │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐                        │
│  │ MODEL      │  │ AGENT RUNNER │  │  SANDBOX    │                        │
│  │ ROUTER     │─►│ tool-use loop│─►│  EXECUTOR   │                        │
│  │            │  │ (max 8 iter) │  │ vfs/git/    │                        │
│  └─────┬──────┘  └──────┬───────┘  │ test/deploy │                        │
│        │                │           └──────┬──────┘                        │
│        │                └──── every tool call re-enters gate2 ────┘        │
│        │                                                                   │
│  ┌─────▼───────────────────────────────────────────────────────────────┐   │
│  │ TELEMETRY EMITTER  ◄── the single choke point. Nothing bypasses it. │   │
│  └─────┬───────────────────────────────────────────────────────────────┘   │
│        │                                                                   │
│  ┌─────▼────────┐   ┌──────────────┐   ┌────────────────────────────────┐  │
│  │ RISK ENGINE  │   │ INCIDENTS    │   │ DATASET EXPORT / POLICY LAB    │  │
│  │ baselines    │──►│ open/merge   │   │ replay over recorded events    │  │
│  │ IsolForest   │   └──────────────┘   └────────────────────────────────┘  │
│  └──────────────┘                                                          │
│                                                                            │
│  ══════════════════ PORTS (abstract) ══════════════════════════════════    │
│    LLMPort · DocStorePort · BlobStorePort · EventBusPort                   │
│    MetricsPort · QueuePort · SecretsPort · ClockPort                       │
│  ════════════════════════════╤═════════════════════════════════════════    │
└───────────────────────────────┼────────────────────────────────────────────┘
                                │  container.py picks ONE column
          ┌─────────────────────┴──────────────────────┐
          ▼                                            ▼
┌──────────────────────────┐              ┌──────────────────────────────┐
│ LOCAL ADAPTERS           │              │ AWS ADAPTERS                 │
│  Ollama / MockLLM        │              │  Amazon Bedrock              │
│  SQLite single-table     │              │  DynamoDB single-table       │
│  Local filesystem        │              │  S3                          │
│  asyncio pub/sub+outbox  │              │  EventBridge                 │
│  stdout metrics          │              │  CloudWatch EMF              │
│  asyncio.Queue           │              │  SQS                         │
│  .env                    │              │  Secrets Manager             │
└──────────────────────────┘              └──────────────────────────────┘
```

---

## 3. The Portability Contract

This is the single most important section. Get this wrong and the AWS migration becomes a rewrite.

### 3.1 The rule

> Domain code depends on **ports**. `container.py` depends on **adapters**. Nothing else ever does.

Enforced mechanically:

```bash
# tests/test_architecture.py runs these as assertions
grep -rn "boto3\|aioboto3"   agentshield/ | grep -v "^agentshield/adapters/aws/" | wc -l   # must be 0
grep -rn "sqlite3\|aiosqlite" agentshield/ | grep -v "^agentshield/adapters/local/" | wc -l # must be 0
grep -rn "AGENTSHIELD_ENV"   agentshield/ | grep -v "container.py\|config.py" | wc -l       # must be 0
grep -rn "from agentshield.adapters" agentshield/ | grep -v "container.py" | wc -l          # must be 0
```

### 3.2 The eight ports

| Port | Method surface | Local | AWS | Notes |
|---|---|---|---|---|
| `LLMPort` | `complete(messages, tools, model, max_tokens) -> LLMResult` | `OllamaAdapter`, `MockLLMAdapter` | `BedrockAdapter` | `LLMResult` carries `text`, `tool_calls[]`, `usage{input,output}`, `model_id`, `stop_reason`. Bedrock Converse API maps 1:1 to this shape — that is why the shape was chosen. |
| `DocStorePort` | `put(item)`, `get(pk, sk)`, `query(pk, sk_prefix, index, limit, cursor)`, `update(pk, sk, patch, condition)`, `batch_put(items)` | `SqliteDocStore` | `DynamoDocStore` | **No joins, no SQL, no scans.** Every access pattern is enumerated in `05-BACKEND-SCHEMA.md §3`. |
| `BlobStorePort` | `put_object(key, bytes, content_type)`, `get_object(key)`, `presign_get(key, ttl)` | `FsBlobStore` (`./.data/blobs/`) | `S3BlobStore` | Holds raw prompts, redaction originals, exported datasets, model payload archives. |
| `EventBusPort` | `publish(envelope)`, `subscribe(handler, types)` | `MemoryBus` + SQLite outbox | `EventBridgeBus` | Envelope is EventBridge-shaped from day one: `{source, detail_type, detail, time, id}`. |
| `MetricsPort` | `count(name, value, dims)`, `gauge(...)`, `timing(...)` | `StdoutMetrics` | `CloudWatchEmfMetrics` | Local emits the same EMF JSON blob to stdout, so dashboards are portable. |
| `QueuePort` | `enqueue(msg)`, `dequeue(max, wait)` | `AsyncioQueue` | `SqsQueue` | Only used for the fan-out of agent sessions. Sim engine runs in-process locally. |
| `SecretsPort` | `get(name) -> str` | `DotenvSecrets` | `SecretsManagerSecrets` | |
| `ClockPort` | `now_sim()`, `now_wall()`, `advance(sim_seconds)`, `speed` | `SimClock` | `SimClock` (identical) | Deliberately one implementation. Simulated time is domain logic, not infrastructure. |

### 3.3 Contract tests

`tests/contract/` contains one suite per port, parameterised over both implementations:

```python
@pytest.fixture(params=["local", "aws"])
def docstore(request):
    if request.param == "local":
        yield SqliteDocStore(":memory:")
    else:
        with mock_aws():                       # moto
            yield DynamoDocStore(table="test", client=boto3.client("dynamodb"))
```

Every test in the suite runs twice. A migration that breaks parity fails CI before it reaches a deploy. This is what makes the AWS switch a 30-minute job rather than a weekend.

### 3.4 What is *not* abstracted, and why

- **DynamoDB's data model is not abstracted away — it is adopted.** The local store is a DynamoDB emulator, not a relational database with a repository pattern on top. Pretending you have joins locally and discovering you don't in production is the classic failure. Writing single-table access patterns from hour one is mildly annoying and completely safe.
- **EventBridge's envelope is not abstracted — it is adopted.** Local events carry `source`, `detail_type`, `detail`, `time`. Moving to EventBridge means changing the transport, not the payload.
- **Bedrock's Converse tool-use shape is not abstracted — it is adopted.** `LLMResult` mirrors it. Ollama's response is normalised *into* it by the local adapter, which is the correct direction: the local adapter does the translation work, not the domain.

The principle: **abstract the transport, adopt the model.** Ports hide *where* things go, not *what shape* they are.

### 3.5 The migration, concretely

```bash
# 1. Provision (once)
sam deploy --template infra/aws/template.yaml --guided
#    creates: DynamoDB table `agentshield` (PK/SK + GSI1 + GSI2),
#             S3 bucket, EventBridge bus `agentshield-bus`,
#             CloudWatch log group, IAM role with Bedrock invoke

# 2. Flip
export AGENTSHIELD_ENV=aws
export AWS_REGION=ap-south-1
export AGENTSHIELD_TABLE=agentshield
export AGENTSHIELD_BUCKET=agentshield-artifacts
export AGENTSHIELD_BUS=agentshield-bus
export LLM_PROVIDER=bedrock
export BEDROCK_MODEL_DEFAULT=anthropic.claude-3-5-sonnet-20241022-v2:0

# 3. Optionally carry local history over
python infra/scripts/migrate_local_to_aws.py --from .data/agentshield.db --to $AGENTSHIELD_TABLE

# 4. Run
make dev
```

Files that changed: `container.py` (already written to branch), `infra/`, `.env`. Files that did not: everything in `domain/`, `sim/`, `governance/`, `agent/`, `risk/`, `telemetry/`, `api/`, and the whole frontend.

---

## 4. Mode Parity: How Simulation and Live Mode Stay Identical

The temptation is to let the simulator call internal functions and Live Mode call an API wrapper. That drifts within a day. Instead:

```
SimulationEngine ─┐
                  ├──► build RequestContext ──► gate1.evaluate() ──► Decision
/ingest/gate1 ────┘

SimulationEngine ─┐
                  ├──► build ActionContext ───► gate2.evaluate() ──► Decision
/ingest/gate2 ────┘
```

`RequestContext` and `ActionContext` are Pydantic models that carry *everything* a gate needs and nothing about where it came from. The only field that differs is `source: Literal["sim", "live"]`, which is telemetry metadata and is **forbidden from appearing in any policy condition** (validated by the DSL schema).

The parity test, which must exist before Phase 5 is complete:

```python
def test_mode_parity(fixture_request):
    via_sim  = gate1.evaluate(build_context_from_sim(fixture_request))
    via_http = client.post("/api/v1/ingest/gate1", json=fixture_request.model_dump()).json()
    assert via_sim.decision == via_http["decision"]
    assert via_sim.matched_policies == via_http["matched_policies"]
```

---

## 5. Gate 1 — Request Governance

### 5.1 Inputs (`RequestContext`)

```
actor      : id, role, team, seniority, allowed_repositories, daily_budget_usd,
             spend_today_usd, risk_score, sessions_today, is_low_confidence
request    : task_type, complexity, repo, environment, prompt_text, prompt_len,
             attachments[], requested_model
derived    : est_input_tokens, est_output_tokens, est_cost_usd, routed_model,
             sensitive_findings[], off_hours (bool), sim_ts
```

### 5.2 Algorithm

```
1. classify(task_type, complexity)            → from persona / caller-supplied, validated
2. scan(prompt_text)                          → sensitive_findings[]   (§5.3)
3. estimate(prompt, task_type)                → est_input/output_tokens
4. route(complexity, policy_hints)            → routed_model + price    (§5.4)
5. est_cost = tokens × price
6. budget.check(actor, est_cost)              → ok | would_exceed
7. risk = risk.current(actor)                 → 0–100, read-only snapshot
8. policy_engine.match(gate=1, context)       → matched[] with effects
9. resolve():
     if budget.would_exceed          → BLOCK  reason=budget_exceeded
     if any(effect == block)         → BLOCK  reason=policy(<id>)
     if any(effect == review)        → REVIEW → approvals.request(...)
     if sensitive_findings non-empty → REDACT (and continue)
     else                            → ALLOW
10. emit(gate1.decision)  — with matched_policies, findings (masked), estimates
```

Precedence is fixed and never configurable: **block > review > redact > allow**. Within the same effect, higher `priority` wins for attribution; the decision is unchanged.

### 5.3 Secret detection (7 detectors, `governance/redaction.py`)

| Detector | Pattern (regex, illustrative) | Action |
|---|---|---|
| AWS access key | `AKIA[0-9A-Z]{16}` | redact |
| AWS secret key | `(?i)aws_secret[^\n]{0,20}[A-Za-z0-9/+=]{40}` | redact |
| Private key block | `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----` | redact + risk bump |
| Generic API token | `(?i)(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}` | redact |
| JWT | `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}` | redact |
| Password assignment | `(?i)password\s*[:=]\s*['\"][^'\"]{6,}` | redact |
| Connection string | `(?i)(postgres|mysql|mongodb)(\+srv)?://[^\s]+:[^\s]+@` | redact |

Redaction replaces the match with `«REDACTED:aws_access_key:a3f9»` where the suffix is the first 4 hex of the SHA-256 — enough to correlate repeats without revealing the value. The original prompt is written to the blob store under `raw/{task_id}/prompt.json`, and reading it emits an `audit.raw_access` event. **The raw value is never written into an event payload, never logged, never sent to the frontend.**

### 5.4 Model router

| Complexity | Default model (AWS) | Default model (local) | Input $/1M | Output $/1M |
|---|---|---|---|---|
| `trivial` | `anthropic.claude-3-5-haiku-20241022-v1:0` | `qwen2.5-coder:1.5b` | 0.80 | 4.00 |
| `standard` | `anthropic.claude-3-5-haiku-20241022-v1:0` | `qwen2.5-coder:7b` | 0.80 | 4.00 |
| `complex` | `anthropic.claude-3-5-sonnet-20241022-v2:0` | `qwen2.5-coder:7b` | 3.00 | 15.00 |

Price tables live in `agent/router.py::PRICE_TABLE` and are the single source for every cost figure in the product. Policies can force a downgrade (`effect: allow` with `route_override`), which is exactly the "interns may not use advanced models for LOW complexity tasks" rule from the brief, and is how the Policy Lab demonstrates savings.

---

## 6. Gate 2 — Action Governance

### 6.1 The eight tools

| Tool | Args | Default sensitivity | Typical governance |
|---|---|---|---|
| `read_file` | `repo, path` | low, unless path matches secret pattern → **critical** | block on secrets; review outside allowed repos |
| `edit_file` | `repo, path, diff` | medium | review outside allowed repos |
| `run_tests` | `repo, suite` | low | allow |
| `git_commit` | `repo, branch, message` | medium | allow on feature branches; review on `main` |
| `git_push` | `repo, branch` | medium–high | review on protected branches |
| `call_api` | `service, method, path` | medium; **high** if `environment=production` | review in prod |
| `deploy` | `repo, environment` | **critical** for production | review (engineer) / allow (devops) / block (intern) |
| `external_fetch` | `url` | **high** — always | block unless host in allowlist |

### 6.2 Inputs (`ActionContext`)

```
actor        : same as Gate 1
task         : id, repo, environment, elapsed_sim_s, tokens_so_far, cost_so_far,
               actions_so_far, blocked_so_far
action       : tool, args, args_digest, target_resource, resource_sensitivity,
               environment, iteration_index
derived      : is_repo_in_scope, is_secret_path, is_protected_branch,
               is_external_host, repeat_count_5m, risk_score
```

### 6.3 Algorithm

```
1. resolve_resource(tool, args)          → target_resource, sensitivity, flags
2. scope.check(actor, repo, env, tool)   → in_scope | out_of_scope
3. risk = risk.current(actor)
4. policy_engine.match(gate=2, context)  → matched[]
5. resolve():
     block > review > allow          (no redact at Gate 2)
6. if REVIEW:
     approval = approvals.request(action, approver=policy.approver, ttl=policy.ttl)
     task.status = awaiting_approval
     emit(approval.requested)         → office badge turns amber
     await approval outcome or expiry
7. if ALLOW: sandbox.execute(action) → ToolResult
   if BLOCK: return ToolRefusal(reason, policy_id) to the agent loop
8. emit(gate2.decision) then emit(sandbox.executed | action.blocked)
```

Critically, a **blocked tool call is returned to the agent as a tool result**, not an exception. The agent sees `{"error": "blocked_by_policy", "reason": "...", "policy": "pol_no_secret_read"}` and continues its loop — usually by trying an alternative. That behaviour is itself telemetry: repeated attempts after a block are one of the strongest adversarial signals in the feature vector.

---

## 7. The Simulation Engine

### 7.1 Why state machines, not 20 LLM agents

Running 20 continuous LLM loops is expensive, slow, non-deterministic and undebuggable. The design instead separates **behaviour volume** from **behaviour fidelity**:

```
20 employees rendered
      ↓
20 persona-driven state machines          ← cheap, deterministic, seeded
      ↓
≤ 4 concurrent agent sessions             ← concurrency cap
      ↓
most sessions: scripted tool sequences    ← MockLLM, ~0 ms, free
      ↓
marquee sessions: real model invocation   ← Bedrock/Ollama, genuine tool use
```

`llm_invocation_rate` (default 0.08) plus explicit scenario flags decide which sessions are real. Every session — scripted or real — travels the identical governance path, so the telemetry is homogeneous.

### 7.2 Employee state machine

```
        ┌──────┐  task assigned   ┌───────────┐
   ┌───►│ IDLE ├─────────────────►│ REQUESTING│
   │    └──────┘                  └─────┬─────┘
   │                                    │ gate1
   │              ┌──────────────┬──────┴──────┬──────────────┐
   │              ▼              ▼             ▼              ▼
   │          BLOCKED      AWAITING_       WORKING        WORKING
   │        (red badge)    APPROVAL      (redacted)      (allowed)
   │              │        (amber)            │              │
   │              │            │ approved     └──────┬───────┘
   │              │            ▼                     ▼
   │              │        WORKING ──────► agent loop: tool → gate2 → sandbox
   │              │            │                     │
   │              │            │ denied/expired      │ max 8 iterations
   │              ▼            ▼                     ▼
   └──────────  DONE ◄──── TERMINATED ◄────────  COMPLETED
                  ▲                                  │
                  └──────────────────────────────────┘
```

Visual states map to office badges: `WORKING`→green, `AWAITING_APPROVAL`→amber, `BLOCKED`→red, `IDLE`→grey, `MEETING`→blue.

### 7.3 Personas

Six archetypes, one JSON template each, instantiated 20 times with seeded jitter:

| Archetype | Count | Experience | Prod access | Token norm | Repo diversity | Daily budget | Mistake p | High-risk p |
|---|---|---|---|---|---|---|---|---|
| `intern` | 5 | low | none | low | low (2 repos) | $8 | 0.07 | 0.01 |
| `engineer` | 6 | medium | none | medium | medium (3) | $20 | 0.04 | 0.01 |
| `senior_engineer` | 3 | high | review | high | medium (4) | $40 | 0.02 | 0.02 |
| `manager` | 2 | high | review | low | low (2) | $15 | 0.02 | 0.01 |
| `senior_manager` | 1 | high | review | low | low (2) | $15 | 0.02 | 0.01 |
| `devops` | 1 | high | allow | medium | high (6) | $35 | 0.03 | 0.03 |
| `ceo` | 1 | — | none | very low | none | $5 | 0.01 | 0.00 |
| **adversarial overlay** | 1 | applied *on top of* an existing engineer/intern persona | | | | | | |

The overlay is the key design decision: employee 17 is a perfectly ordinary `engineer` persona with an extra `scenario_profile: adversarial` field that the *simulator* reads and the *governance and risk code cannot*. To an operator he is indistinguishable from his peers until his behaviour gives him away.

### 7.4 The adversarial ladder

Escalation is time-gated on simulated days so the detector has a genuine signal to find, not a single obvious spike:

| Sim day | Stage | Behaviour injected | Expected first detector to fire |
|---|---|---|---|
| 1–3 | baseline | Normal for his archetype. Establishes his own baseline. | none |
| 4–5 | recon | Reads files in 2–3 repos outside `allowed_repositories`, in-hours | repo-diversity z-score |
| 6–7 | credential probing | `read_file` attempts on `.env*`, `secrets/*` → blocked; retries with path variants | blocked-attempt rate + `args_digest` repeat count |
| 8–9 | egress attempts | `external_fetch` to non-allowlisted hosts; off-hours activity begins | external-attempt count + off-hours fraction |
| 10–11 | volume | Token usage 5–8× his own baseline; long sessions | token z-score, session-length z-score |
| 12+ | restricted ops | `deploy(production)`, `git_push(main)`, `call_api(prod)` | static sensitivity + composite |

Two decoys exist so the detector cannot win by looking for any anomaly at all: a legitimate **release week** (days 9–10) where devops and seniors genuinely spike, and one **sloppy intern** with a high mistake rate and a retry loop that burns budget without being malicious. A detector that flags either is producing a false positive, and the evaluation harness counts it.

### 7.5 Clock and speed

```
SimClock:
  sim_ts             int (simulated unix seconds)
  TICK_SIM_SECONDS   60          # one tick = one simulated minute
  speed              1 | 10 | 100

  1×   → tick every 1000 ms   → WS frame per tick
  10×  → tick every 100 ms    → WS frames coalesced into 250 ms batches
  100× → headless batch loop  → no per-event WS; a progress frame every 250 ms,
                                then one summary frame + snapshot on completion
```

Working hours are modelled: tasks are sampled with a diurnal probability curve peaking 10:00–12:00 and 14:00–17:00, near-zero 01:00–06:00. Off-hours activity is therefore rare and meaningful — which is what makes it a usable feature.

---

## 8. The Risk Engine

### 8.1 Composite score

```
risk = clamp(0, 100,  0.35 · static  +  0.40 · behavioural  +  0.25 · ml)
```

Weights live in `risk/scoring.py::WEIGHTS` and are exposed in the Control Center so a demo can show the blend changing.

**Static (0–100)** — a lookup over `role × tool × environment × resource_sensitivity`. Deterministic, explainable, works from the first event. An intern attempting a production deploy scores 95 here regardless of history.

**Behavioural (0–100)** — rolling z-scores of the employee against **their own** 14-day baseline (falling back to their archetype's baseline below 20 sessions, flagged `low_confidence`):

```
behavioural = 100 · sigmoid( Σ wᵢ · clip(zᵢ, 0, 4) / Σ wᵢ  −  1.0 )
```

over: token volume, cost, off-hours fraction, repo entropy, novel-repo count, blocked-attempt rate, tool diversity, session length.

**ML (0–100)** — IsolationForest (`n_estimators=200`, `contamination=0.03`, seeded) trained nightly (per simulated day) on all sessions from the trailing window. Scores are converted to 0–100 by percentile rank within the training distribution, so the number is interpretable.

### 8.2 The 12-feature session vector

| # | Feature | Definition |
|---|---|---|
| 1 | `tokens_z` | z-score of session total tokens vs actor baseline |
| 2 | `cost_z` | z-score of session cost |
| 3 | `offhours_frac` | fraction of session minutes outside declared work hours |
| 4 | `repo_entropy` | Shannon entropy of repos touched in trailing 7 days |
| 5 | `novel_repo_count` | repos touched this session never touched before |
| 6 | `secret_attempts` | `read_file` attempts on secret-classified paths |
| 7 | `prod_attempts` | actions targeting `environment=production` |
| 8 | `block_rate` | blocked actions ÷ total actions this session |
| 9 | `review_rate` | review decisions ÷ total actions |
| 10 | `tool_diversity` | distinct tools used ÷ 8 |
| 11 | `session_len_z` | z-score of session duration |
| 12 | `external_attempts` | `external_fetch` calls to non-allowlisted hosts |

### 8.3 Label isolation (non-negotiable)

Ground truth is stored at `PK=RUN#<id>, SK=GT#<event_seq>` — a key prefix the risk module has no query for. Enforcement is threefold:

1. `risk/` never imports `sim/scenarios.py` or `sim/persona.py` (import-graph test).
2. `DocStorePort` calls from `risk/` are wrapped by `RiskScopedDocStore`, which raises on any `sk_prefix` beginning `GT#`.
3. `tests/test_label_isolation.py` asserts the feature-vector builder produces identical output when every ground-truth item is deleted from the store.

Ground truth is read by exactly one place: `infra/scripts/evaluate.py`.

### 8.4 Incidents

An incident opens when composite risk crosses 70 for two consecutive sessions, or when any single static-critical event occurs. Subsequent qualifying events within 24 sim-hours merge into the open incident rather than creating new ones. Each incident carries an evidence trail: the contributing events, the feature values at open time, and the policies that fired.

---

## 9. Telemetry

### 9.1 Envelope (EventBridge-shaped from day one)

```json
{
  "id": "evt_01JAV...",
  "source": "agentshield.sim",
  "detail_type": "gate2.decision",
  "time": "2026-09-18T09:21:04Z",
  "detail": {
    "run_id": "run_7f3a",
    "seq": 18412,
    "sim_ts": 1758182464,
    "employee_id": "emp_017",
    "task_id": "task_9c21",
    "payload": { "...": "type-specific" }
  }
}
```

`seq` is a monotonic per-run counter assigned by the emitter. It is the cursor for the Live Feed, the ordering key for replay, and the dedup key for the WebSocket.

### 9.2 The 14 event types

`sim.tick` · `sim.day.completed` · `task.requested` · `gate1.decision` · `model.invoked` · `action.requested` · `gate2.decision` · `approval.requested` · `approval.decided` · `sandbox.executed` · `action.blocked` · `task.completed` · `budget.exceeded` · `risk.updated` · `incident.opened`

(Full payload schemas: `05-BACKEND-SCHEMA.md §5`.)

### 9.3 Fan-out

```
emitter.emit(envelope)
  ├─► DocStore.put   PK=RUN#<id>  SK=EVT#<seq:012d>      (durable, queryable, replayable)
  ├─► EventBus.publish(envelope)                          (local: in-proc; aws: EventBridge)
  ├─► WS broadcaster                                      (coalesced by speed)
  ├─► MetricsPort.count(...)                              (stdout EMF / CloudWatch)
  └─► RiskEngine.observe(envelope)                        (incremental feature accumulation)
```

The emitter is synchronous to the DocStore and fire-and-forget to the rest. If the WebSocket is down, nothing else is affected — a property the office view depends on for rehydration.

---

## 10. Policy Engine

### 10.1 DSL

```json
{
  "id": "pol_prod_deploy_requires_manager",
  "version": 3,
  "gate": 2,
  "priority": 100,
  "effect": "review",
  "enabled": true,
  "is_draft": false,
  "when": {
    "all": [
      { "field": "action.tool", "op": "eq", "value": "deploy" },
      { "field": "action.environment", "op": "eq", "value": "production" },
      { "field": "actor.role", "op": "not_in", "value": ["devops"] }
    ]
  },
  "approver": { "role": "manager", "scope": "team" },
  "ttl_sim_seconds": 300,
  "message": "Production deployment requires manager approval."
}
```

Operators: `eq`, `neq`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `matches` (regex), `contains`, `exists`. Combinators: `all`, `any`, `none`. Fields are a fixed allowlist per gate, published in `packages/contracts/policy-fields.json` — an unknown field is a validation error with a JSON path, not a silent no-match.

`source` (sim vs live) is deliberately **absent from the field allowlist**. Policies cannot behave differently between modes.

### 10.2 Evaluation

Policies for a gate are loaded once and cached in memory, invalidated on write. Evaluation is a linear scan over the enabled set — with ~20 policies and ~200 evaluations/sec this is far below the 50 ms p95 budget and keeps the trace trivially explainable. If it ever matters, index by `(gate, tool)` first; do not reach for a rules engine.

### 10.3 Policy Lab (replay)

```
draft policy + window (default 24 sim-hours)
      ↓
load events: PK=RUN#<id>, SK between EVT#<a> and EVT#<b>
      ↓
rebuild the RequestContext / ActionContext for each decision event
      ↓
re-evaluate with (enabled policies ∪ {draft})
      ↓
diff against the recorded decision
      ↓
report:
   requests_affected, projected_spend_delta_usd,
   newly_blocked_but_previously_succeeded   ← false-positive proxy
   newly_blocked_and_previously_blocked     ← redundant coverage
   extra_approvals_per_day
```

Replay is possible only because every decision event stores the full context snapshot it was evaluated against. That is a deliberate storage cost (~2 KB/decision) paid for this feature and for audit.

---

## 11. Frontend Architecture

```
WebSocket ──► ws.ts ──► telemetryStore (Zustand)
                            │
        ┌───────────────────┼─────────────────────┐
        ▼                   ▼                     ▼
   bridge.ts           Live Feed            Approvals badge
   (drains a queue,    (virtualised,        (count only)
    60 fps, into        capped at 2 000)
    Phaser)
        │
        ▼
   OfficeScene.applyEvent(e)   ← the ONLY way office visuals change
```

Rules that keep the office honest:

- **Phaser never fetches.** No `fetch`, no WebSocket, no API import inside `src/game/`.
- **`bridge.ts` drains, it does not subscribe per-avatar.** One `requestAnimationFrame` loop pulls up to N events per frame and dispatches into the scene. Backpressure is a visual concern only.
- **Office state is derived, never authoritative.** On mount, reload, or exiting 100× mode, the scene rebuilds from `GET /sim/runs/{id}/state` and then resumes the stream at `seq > snapshot.seq`.
- **REST and WS never write to the same store slice.** `simStore` holds run + employee snapshot state (REST-owned); `telemetryStore` holds the event stream (WS-owned). The office reads both; nothing reconciles them, because they never overlap.

---

## 12. Failure Modes and Their Handling

| Failure | Detection | Handling |
|---|---|---|
| LLM provider unreachable | timeout / connection error in adapter | fall back to `MockLLM` for that session, emit `model.invoked` with `fallback=true`, banner in Live Feed. The simulation never stalls on a model. |
| LLM returns malformed tool call | schema validation in `agent/runner.py` | count as an agent error, return a correction message to the model, retry once, then terminate the session as `failed` |
| Agent loops (same `args_digest` ≥ 3 times in 5 min) | `repeat_count_5m` in `ActionContext` | seeded policy `pol_retry_loop_guard` → block with `reason=retry_loop`; counted as waste |
| Approval never answered | TTL sweep on every tick | `expired` → task `denied_timeout` |
| WebSocket drops | client heartbeat | exponential backoff reconnect, resume from last `seq`, office resnapshots if the gap exceeds 500 events |
| DocStore write fails | adapter raises | emitter retries 3× with jitter; on final failure, event goes to a local dead-letter file and a `telemetry.degraded` banner shows. Governance decisions are never blocked by telemetry failure. |
| Sim tick overruns its budget at 10× | tick duration measured | drop to the next lower speed automatically and surface a toast; never let ticks queue up |
| Browser has no WebGL | Phaser init failure | office falls back to the card-grid view (`07-OFFICE-SIMULATION.md §11`) |
| Bedrock throttling (AWS) | `ThrottlingException` | exponential backoff in `BedrockAdapter` only; domain code sees a normal slow call |

---

## 13. Security Design

Even though v1 has no auth, these hold:

- **Secrets never round-trip to the client.** Redaction happens server-side before persistence. The frontend receives only masked forms.
- **The blob store is the only home for raw prompts**, and every read emits an audit event.
- **Live Mode ingest is bearer-token authenticated per agent identity**, with the token mapped to an `actor_id`. An agent cannot assert its own role — role comes from the registered identity, server-side.
- **Policy writes are versioned and append-only.** Editing creates version N+1; the old version stays for audit and for replay fidelity.
- **The simulation cannot reach the network.** The sandbox `external_fetch` tool never performs a real request; it consults an allowlist and returns a canned response. This is both a security property and a determinism property.
- **IAM on AWS is least-privilege per port**: the task role gets `dynamodb:{PutItem,GetItem,Query,UpdateItem}` on one table, `s3:{PutObject,GetObject}` on one prefix, `events:PutEvents` on one bus, `bedrock:InvokeModel` on the two allowed model ARNs. Nothing else.

---

## 14. Decisions Log

| # | Decision | Alternatives considered | Why |
|---|---|---|---|
| D1 | FastAPI backend, not Next.js API routes | Next.js full-stack | scikit-learn, boto3, and a long-running asyncio tick loop all live naturally in Python; a Node backend would need a second Python service anyway |
| D2 | Vite SPA, not Next.js | Next.js | the backend is FastAPI, so SSR buys nothing; Phaser wants a plain client bundle; faster HMR for game iteration |
| D3 | DynamoDB single-table shape used locally in SQLite | Postgres locally + DynamoDB in prod; Postgres everywhere | eliminates the entire class of "works locally, breaks in prod" storage bugs; the whole point of the portability goal |
| D4 | State machines + selective LLM calls | 20 continuous LLM agents | cost, latency, determinism, debuggability — all four fail with the alternative |
| D5 | Ground truth stored under an unreachable key prefix | a boolean column on the employee row | a column is one accidental `SELECT *` away from leaking into features |
| D6 | Blocked tool calls returned as tool results, not exceptions | raise and terminate | the agent's *reaction* to a block is the richest adversarial signal available |
| D7 | Phaser, not a hand-rolled canvas renderer | custom canvas; DOM/CSS sprites; Three.js | sprite batching, tilemaps, tweens and camera are free; the brief explicitly warns against building a game engine |
| D8 | Full context snapshot stored on every decision event | store IDs and rebuild by joining | replay and audit both need the exact evaluated context; storage is cheap, correctness is not |
| D9 | One `ClockPort` implementation for both environments | wall clock in prod | simulated time is domain logic; abstracting it would invite a real-clock code path that breaks determinism |
| D10 | Unsupervised detection only | supervised classifier on the adversarial label | training on the label makes every evaluation number meaningless; the brief's own principle |
