# AgentShield — Implementation Plan

> Nine phases, mapped onto four days. Each phase has entry criteria, atomic tasks naming exact files, and a verification block you must run and pass before moving on.

---

## Build Philosophy

**Build the spine before the skin.** The governance core (gates, agent, telemetry) is the product; the simulation drives it; the dashboards read it; the office renders it. Build in that order and every phase leaves you with something demonstrable. Build the office first and you will spend four days on a game and demo a game.

**Build vertically inside each phase.** Phase 2 delivers the policy engine *and* its tests *and* a CLI you can run. Never leave a phase with code that has no way to be exercised.

**Two things are never deferred:** the ports boundary (Phase 0) and the telemetry choke point (Phase 1). Both are architecture, and retrofitting either costs more than the whole build.

### Day map

| Day | Phases | You can demo… |
|---|---|---|
| 1 | 0, 1, 2 | gates deciding, in a terminal |
| 2 | 3, 4, 5 | a simulated company generating governed telemetry, over an API |
| 3 | 6, 7 | the full console: live feed, approvals, control centre, risk |
| 4 | 8, 9 | the office, the policy lab, AWS, the recorded demo |

If you fall behind, the cut order is: office polish (V6–V8) → Policy Lab → AWS adapters → exec view. Never cut the risk engine, and never cut the contract tests.

---

## Phase 0 — Scaffold, Ports, Container

**Entry:** empty directory. **Exit:** both services boot; contract tests pass against both adapter sets; the architecture guard passes.

### Commands

```bash
mkdir -p agentshield && cd agentshield
git init && git commit --allow-empty -m "chore: init"

# ── Backend ──
mkdir -p services/api/agentshield/{domain,ports,adapters/local,adapters/aws,sim,governance,agent,sandbox,risk,telemetry,api}
mkdir -p services/api/tests/{contract,unit,e2e}
cd services/api
python3.11 -m venv .venv && source .venv/bin/activate
pip install fastapi==0.115.* "uvicorn[standard]==0.32.*" pydantic==2.9.* \
  pydantic-settings==2.6.* aiosqlite==0.20.* boto3==1.35.* aioboto3==13.2.* \
  httpx==0.27.* scikit-learn==1.5.* numpy==2.1.* pandas==2.2.* pyarrow==17.* \
  ulid-py==1.1.* pyyaml==6.0.* structlog==24.4.*
pip install pytest==8.3.* pytest-asyncio==0.24.* pytest-benchmark==4.0.* \
  "moto[dynamodb,s3,events]==5.0.*" ruff==0.7.* mypy==1.13.*
pip freeze > requirements.txt
cd ../..

# ── Frontend ──
npm create vite@latest apps/web -- --template react-ts
cd apps/web
npm install react-router-dom@7 zustand@5 @tanstack/react-query@5 \
  @tanstack/react-virtual@3 phaser@3.90 recharts@2 lucide-react \
  date-fns@4 clsx tailwind-merge @uiw/react-codemirror @codemirror/lang-json
npm install -D tailwindcss@4 @tailwindcss/vite vitest @testing-library/react
cd ../..

mkdir -p packages/contracts infra/aws infra/scripts scenarios docs
```

### Files

| File | Contents |
|---|---|
| `services/api/agentshield/config.py` | `Settings(BaseSettings)` with every variable from `02-TRD.md §4` |
| `services/api/agentshield/ports/*.py` | the 8 Protocols from `02-TRD.md §3.4`. **No implementations.** |
| `services/api/agentshield/adapters/local/sqlite_docstore.py` | schema + `put/get/query/update/batch_put` per `02-TRD.md §5.2` |
| `services/api/agentshield/adapters/local/{fs_blobstore,memory_eventbus,stdout_metrics,mock_llm,asyncio_queue,dotenv_secrets}.py` | |
| `services/api/agentshield/adapters/aws/{dynamo_docstore,s3_blobstore,eventbridge_bus,cloudwatch_metrics,bedrock_llm,sqs_queue}.py` | write these **now**, while the port shapes are fresh — not in Phase 9 |
| `services/api/agentshield/container.py` | exactly as in `02-TRD.md §5.1` |
| `services/api/agentshield/main.py` | FastAPI app, lifespan opens/closes the container, `/healthz`, `/readyz` |
| `services/api/tests/contract/test_docstore_contract.py` | parameterised over `["local","aws"]`, moto for aws |
| `services/api/tests/contract/test_{eventbus,blobstore,llm}_contract.py` | same pattern |
| `services/api/tests/test_architecture.py` | the four greps from `DESIGN.md §3.1`, as assertions |
| `apps/web/vite.config.ts` | `@tailwindcss/vite` plugin, `@` alias to `src`, proxy `/api` → `:8000` |
| `apps/web/src/styles/globals.css` | the full block from `04-UI-UX-BRIEF.md §10` |
| `Makefile` | `dev`, `api`, `web`, `test`, `seed`, `seed-history`, `demo`, `export-dataset`, `evaluate`, `repro-check` |
| `.env.example` | the full block from `02-TRD.md §4` |

### Verify

```bash
make test-contract     # every port suite green against BOTH local and aws
pytest tests/test_architecture.py -v
make dev               # api on :8000, web on :5173
curl -s localhost:8000/healthz | jq
# → { "status": "ok", "env": "local", "adapters": { "docstore": "SqliteDocStore", ... } }
git commit -am "feat(phase-0): ports, adapters, container, contract tests"
```

**Do not proceed if any contract test is skipped for the aws parameter.** That skip is the migration failing eight days early.

---

## Phase 1 — Domain, Storage, Telemetry

**Entry:** Phase 0 green. **Exit:** you can write an event and read it back, locally and under moto.

### Tasks

- `domain/enums.py` — every enum from `02-TRD.md §3.1`
- `domain/models.py` — every model from `02-TRD.md §3.2` and `§3.3`
- `domain/events.py` — `EventEnvelope`, `EventDetail`, and the 14 payload models from `05-BACKEND-SCHEMA.md §5`
- `packages/contracts/events.schema.json` + `generate.py` → writes `apps/web/src/types/generated.ts`
- `telemetry/emitter.py` — exactly the shape in `02-TRD.md §5.5`, including the sequence counter (`SEQ#<run_id>/EVENT`, atomic increment) and the separate ground-truth key
- `telemetry/counters.py` — the six counters from `05-BACKEND-SCHEMA.md §4`
- `adapters/local/sqlite_docstore.py` — implement `update(patch={"$add": …})`
- `risk/scoped_store.py` — `RiskScopedDocStore` from `05-BACKEND-SCHEMA.md §3.3`
- `tests/unit/test_emitter.py`, `tests/test_label_isolation.py`

### Verify

```bash
python -m agentshield.scripts.smoke_emit --run-id run_test --count 100
sqlite3 .data/agentshield.db \
  "SELECT sk FROM items WHERE pk='RUN#run_test' ORDER BY sk LIMIT 3;"
# → EVT#000000000001 / EVT#000000000002 / EVT#000000000003
pytest tests/test_label_isolation.py -v     # feature vectors identical with GT# deleted
git commit -am "feat(phase-1): domain models, single-table store, telemetry emitter"
```

---

## Phase 2 — Policy Engine and Both Gates

**Entry:** Phase 1 green. **Exit:** gates decide correctly, headlessly, with p95 under 50 ms.

### Tasks

- `governance/dsl.py` — `validate(when, gate)` and `evaluate(when, context) -> bool`. Field allowlists from `05-BACKEND-SCHEMA.md §7.2`. Depth ≤ 5, conditions ≤ 25.
- `governance/policy_engine.py` — load, cache, invalidate on write; `match(gate, ctx) -> list[PolicyMatch]`; precedence `block > review > redact > allow`
- `governance/redaction.py` — the 7 detectors from `DESIGN.md §5.3`; returns findings + masked text; originals to the blob store
- `governance/budget.py` — per-employee and per-team daily checks against the counters
- `governance/gate1.py` — the 10-step algorithm from `DESIGN.md §5.2`
- `governance/gate2.py` — the 8-step algorithm from `DESIGN.md §6.3`
- `governance/approvals.py` — request, decide, TTL sweep; the state machine from `05-BACKEND-SCHEMA.md §9`
- `agent/router.py` — `PRICE_TABLE` and `route(complexity, overrides)`
- `sim/seed.py` — the 12 policies from `05-BACKEND-SCHEMA.md §10.3` (employees come in Phase 4)
- `tests/unit/test_dsl.py`, `test_precedence.py`, `test_gate1.py`, `test_gate2.py`, `test_redaction.py`, `test_approvals.py`

### Verify

```bash
make seed-policies
python -m agentshield.scripts.gate_repl
# > gate1 intern trivial payments-api production "fix the bug, key is AKIAIOSFODNN7EXAMPLE"
# decision=redact  findings=[aws_access_key]  routed=haiku  est=$0.0031
# > gate2 intern read_file payments-api .env.production
# decision=block   policy=pol_block_secret_read (v1, p200)
# > gate2 devops deploy payments-api production
# decision=allow
# > gate2 engineer deploy payments-api production
# decision=review  approver=manager/team  ttl=300

pytest tests/unit -k "gate or dsl or precedence or redaction" -v
pytest tests/unit/test_gate_perf.py --benchmark-only    # p95 < 50 ms
grep -r "AKIAIOSFODNN7EXAMPLE" .data/agentshield.db     # → no matches. Ever.
git commit -am "feat(phase-2): policy DSL, gate 1, gate 2, approvals"
```

**This is the phase to be slow and careful in.** Everything downstream assumes the gates are right.

---

## Phase 3 — Agent Runner and Sandbox

**Entry:** Phase 2 green. **Exit:** an agent completes a task through both gates, with mock and with a real local model.

### Tasks

- `agent/tools.py` — JSON schemas for the 8 tools (`DESIGN.md §6.1`)
- `agent/prompts.py` — system prompt, task prompt builder, tool-result formatting
- `agent/runner.py` — the loop from `02-TRD.md §5.4`. Blocks return as tool results, never exceptions.
- `sandbox/vfs.py` — virtual repos in the DocStore (`REPO#<name>/FILE#<path>`); seeded file trees per repo
- `sandbox/git_ops.py` — commit/push against the virtual tree, protected-branch detection
- `sandbox/test_runner.py` — seeded pass/fail, biased by the employee's `mistake_probability`
- `sandbox/deploy.py` — simulated deploy with a latency draw; records environment
- `adapters/local/mock_llm.py` — scripted tool sequences per `task_type`, seeded and deterministic
- `adapters/local/ollama_llm.py` — normalises Ollama's response into `LLMResult`
- `tests/unit/test_runner.py`, `tests/unit/test_sandbox.py`

### Verify

```bash
LLM_PROVIDER=mock python -m agentshield.scripts.run_task \
  --employee emp_013 --task "Fix payment API error" --repo payments-api --env production
# read_file src/handlers/payment.py   ALLOW
# run_tests payments-api              ALLOW   (2 failed)
# edit_file src/handlers/payment.py   ALLOW
# run_tests payments-api              ALLOW   (passed)
# read_file .env.production           BLOCK   pol_block_secret_read
# deploy payments-api production      REVIEW  → approval appr_… pending
# task status: awaiting_approval

ollama pull qwen2.5-coder:7b
LLM_PROVIDER=ollama python -m agentshield.scripts.run_task --employee emp_007 --task "Add a unit test for the refund path"
# must produce genuine, varied tool calls — not the mock's script

pytest tests/unit/test_runner.py -v
git commit -am "feat(phase-3): agent runner, 8 tools, sandbox, mock + ollama adapters"
```

---

## Phase 4 — The Simulation Engine

**Entry:** Phase 3 green. **Exit:** 20 employees generate reproducible governed telemetry; a week fast-forwards in under 20 s.

### Tasks

- `sim/persona.py` — 6 archetype templates + the adversarial overlay (`DESIGN.md §7.3`)
- `sim/seed.py` — the 20 employees from `05-BACKEND-SCHEMA.md §10.2`, 6 repos with file trees, desk assignments
- `sim/task_generator.py` — diurnal sampling, task type by persona, complexity draw, `is_marquee` flag
- `sim/scenarios.py` — YAML loader; the adversarial ladder (`DESIGN.md §7.4`); the sloppy-intern and release-week decoys
- `sim/engine.py` — tick loop, `SimSpeed`, concurrency cap of 4, approval TTL sweep per tick, auto-downshift on overrun
- `sim/snapshot.py` — `OfficeSnapshot` builder
- `ports/clock.py` + `SimClock` — the only implementation
- `scenarios/demo.yaml` — the scripted beats for the recorded demo (§ Phase 9)
- `tests/unit/test_determinism.py`, `tests/unit/test_scheduler.py`

### Verify

```bash
make seed && make seed-history      # 20 employees + 14 sim-days of baseline
time make advance DAYS=7            # must be < 20s with LLM_PROVIDER=mock

make repro-check
# runs the same seed twice, hashes both event streams, asserts equality
# → sha256 a7f3… == a7f3…  ✓ reproducible

python -m agentshield.scripts.sim_stats --run-id $RUN
# employees 20 | archetypes 6 | adversarial 1 | sloppy 1
# tasks 4,812 | blocked 71 | approvals 34 | cost $184.22
# max concurrent sessions observed: 4

pytest tests/unit/test_determinism.py -v
git commit -am "feat(phase-4): personas, task generator, tick loop, scenarios"
```

**If `repro-check` fails**, you have a module-level `random` call or a dict-ordering dependency. Find it now — every number the detector produces later is worthless without this.

---

## Phase 5 — API and WebSocket

**Entry:** Phase 4 green. **Exit:** every endpoint in `05-BACKEND-SCHEMA.md §6` responds correctly; Live Mode parity is proven.

### Tasks

- `api/routes_sim.py`, `routes_employees.py`, `routes_tasks.py`, `routes_events.py`, `routes_approvals.py`, `routes_policies.py`, `routes_risk.py`, `routes_metrics.py`
- `api/routes_ingest.py` — the three Live Mode endpoints, bearer auth from `INGEST_TOKENS`, rate limit
- `api/ws.py` — `/ws/stream`, `since` cursor, speed-aware coalescing, heartbeat every 15 s
- `api/errors.py` — the global handler and the error envelope from `02-TRD.md §6.1`
- `deps.py` — container-backed dependency providers
- `infra/scripts/reference_client.py` — the < 60-line Live Mode demo client
- `tests/e2e/test_api.py`, `tests/e2e/test_mode_parity.py`

### Verify

```bash
curl -sX POST localhost:8000/api/v1/sim/runs -d '{"seed":20260918}' -H 'content-type: application/json' | jq .data.run_id
curl -s "localhost:8000/api/v1/employees?run_id=$RUN" | jq 'length'          # → 20
curl -s "localhost:8000/api/v1/employees?run_id=$RUN" | jq '.data[0] | has("scenario_profile")'   # → false
curl -s "localhost:8000/api/v1/sim/runs/$RUN/state" | jq '.data.avatars | length'  # → 20

websocat "ws://localhost:8000/ws/stream?run_id=$RUN&since=0" | head -5

pytest tests/e2e/test_mode_parity.py -v   # sim path and /ingest path give identical decisions
python infra/scripts/reference_client.py  # full request → tool → approval round trip
git commit -am "feat(phase-5): REST API, WebSocket, live-mode ingest"
```

---

## Phase 6 — The Console

**Entry:** Phase 5 green. **Exit:** Live Feed, Approvals and Control Center all work against the real API.

### Tasks

- `src/styles/globals.css` — paste `04-UI-UX-BRIEF.md §10` verbatim; load the three fonts
- `src/lib/api.ts` (typed fetch + error envelope), `src/lib/ws.ts` (`02-TRD.md §5.6`), `src/lib/format.ts` (`describeEvent`, token/money humanising), `src/lib/risk.ts` (`riskColor`)
- `src/stores/{simStore,telemetryStore,uiStore}.ts` — the split from `DESIGN.md §11`
- `src/components/layout/{AppShell,HeaderNav,SpeedControl,RunPill,SimClock,RoleSelector,ConnectionDot}.tsx`
- `src/components/ui/{Button,Chip,DecisionChip,StatusChip,Card,StatCard,Table,Drawer,Dialog,Toast,Skeleton,EmptyState,RiskMeter}.tsx` — every one from `04-UI-UX-BRIEF.md §5`
- `src/routes/live.tsx` + `components/live/{FeedTable,FeedFilters,TracePanel}.tsx`
- `src/routes/approvals.tsx` + `components/approvals/{ApprovalCard,DecidedTable}.tsx`
- `src/routes/control/{index,policies,employees,costs}.tsx` + `components/control/*`
- `src/components/employee/EmployeeDrawer.tsx` — shared by office and control
- `src/components/office/AvatarGrid.tsx` — **build this now**, it is the office until Phase 8

### Verify

```bash
cd apps/web && npm run build            # zero TS errors
npm run dev
# Manually, against a running sim:
#  · Live Feed streams; pause buffers; resume flushes
#  · Filters narrow correctly; row expands to a full trace
#  · An approval appears within 1s of the policy firing
#  · Approving resumes the task; the Live Feed shows approval.decided
#  · Control overview numbers match `curl /api/v1/metrics/summary`
#  · Every list has a real empty state (stop the sim and reload)
#  · Kill the API → error states appear, nothing crashes, retry works
git commit -am "feat(phase-6): console — live feed, approvals, control center"
```

---

## Phase 7 — Risk, Incidents, Evaluation

**Entry:** Phase 6 green, with ≥ 2 000 sessions of history. **Exit:** the detector finds the hidden actor without ever seeing the label.

### Tasks

- `risk/features.py` — the 12-feature vector (`DESIGN.md §8.2`), built through `RiskScopedDocStore` only
- `risk/baseline.py` — rolling per-employee stats, archetype fallback under 20 sessions
- `risk/scoring.py` — composite blend, `top_factors`, plain-language explanations (the wording lives here)
- `risk/isolation.py` — IsolationForest train + percentile scoring, seeded
- `risk/incidents.py` — open at ≥ 70 for two consecutive sessions or any static-critical event; merge within 24 sim-hours
- `api/routes_risk.py` — `/explain` with baseline comparison
- `src/routes/control/{risk,incidents}.tsx`
- `infra/scripts/evaluate.py` — **the only file permitted to read `GT#`**
- `tests/unit/test_features.py`, `test_scoring.py`, `tests/test_no_label_leakage.py`

### Verify

```bash
make advance DAYS=30
make train-risk
make evaluate
# ── AgentShield detection evaluation ──────────────
# sessions            6,140
# flagged (≥70)         214
# adversarial actor   emp_017
# recall               0.86
# precision            0.71
# false positives        62   (of which sloppy-intern 41, release-week 18)
# time to detection    1.7 simulated days after stage 2
# ──────────────────────────────────────────────────

pytest tests/test_no_label_leakage.py -v
curl -s "localhost:8000/api/v1/risk/employees/emp_017/explain?run_id=$RUN" | jq '.data.top_factors'
# → three factors with plain-language explanations, not raw feature names
git commit -am "feat(phase-7): risk engine, incidents, evaluation harness"
```

**Tuning note.** If recall is low, the adversarial ladder is probably too gentle — widen the token multiplier or add a stage. If false positives are high, check whether the release-week decoy is being flagged: that is the interesting failure, and it is worth mentioning honestly in the demo rather than tuning away.

---

## Phase 8 — The Office

**Entry:** Phase 7 green. **Exit:** the acceptance checklist in `07-OFFICE-SIMULATION.md §14`.

Follow the V0–V8 build order in `07-OFFICE-SIMULATION.md §13` exactly. It is already atomic and time-boxed. **Respect the cut line at V5.**

### Verify

```bash
npm run build
# Open /office and confirm, item by item, the §14 checklist.
grep -rn "fetch\|axios\|WebSocket" apps/web/src/game/     # → nothing
# Chrome Performance: 20 avatars at 10× → game.loop.actualFps ≥ 50
# DevTools → Rendering → Emulate prefers-reduced-motion: no tweens, states still change
git commit -am "feat(phase-8): isometric office view"
```

---

## Phase 9 — Policy Lab, AWS, Demo

**Entry:** Phase 8 green. **Exit:** deployed, recorded, documented.

### 9a — Policy Lab

- `telemetry/replay.py` — rebuild contexts from stored snapshots; re-evaluate with the draft
- `api/routes_policy_lab.py`
- `src/routes/control/policy-lab.tsx`

```bash
curl -sX POST localhost:8000/api/v1/policy-lab/simulate \
  -d @fixtures/draft_intern_downgrade.json -H 'content-type: application/json' | jq .data
# requests_affected 218 (8.4%) | savings −$21.40 (21%) | newly blocked that
# previously succeeded 3 | extra approvals/day 14      — and it returns in < 5s
```

### 9b — Executive view

- `src/routes/control/index.tsx` — the six stats, spend by team, risk by team, the "why is Payments high?" panel, the 7-day trend
- Role adaptation from `03-APP-FLOW.md §9`

### 9c — AWS

The adapters already exist and already pass contract tests. This step is provisioning only.

```bash
sam deploy -t infra/aws/template.yaml --guided
#  → DynamoDB table (PK/SK + gsi1 + gsi2, on-demand, PITR on)
#  → S3 bucket (block public access, SSE-S3)
#  → EventBridge bus + rules
#  → CloudWatch log group
#  → IAM role: least-privilege per DESIGN.md §13
#  → App Runner service from ECR

aws bedrock list-foundation-models --region $AWS_REGION \
  | jq '.modelSummaries[] | select(.modelId|test("claude")) | .modelId'
# Confirm both model ids are available in this region BEFORE demo day.

export AGENTSHIELD_ENV=aws LLM_PROVIDER=bedrock
python infra/scripts/migrate_local_to_aws.py --from .data/agentshield.db --to $AGENTSHIELD_TABLE
make dev && curl -s localhost:8000/healthz | jq .adapters

git diff --stat HEAD~1   # must touch only adapters/aws, container.py, infra/ — nothing else
```

### 9d — The demo

`scenarios/demo.yaml` scripts these beats on a sim clock, so `make demo` is unattended and identical every run:

| t | Beat | What the audience sees |
|---|---|---|
| 0:00 | Office at 1×, twenty characters working | green badges, the system log ticking |
| 0:20 | Rahul (intern) asks the agent to fix authentication | bubble over his head, Gate 1 allows, Live Feed row |
| 0:35 | Agent reads files, runs tests | green rows accumulating |
| 0:50 | Agent attempts `read_file .env.production` | **Rahul turns red**, the log prints the block, the dashboard shows the secret protected |
| 1:10 | Priya's session spikes to 6× tokens | amber cost-anomaly badge |
| 1:25 | Aman's agent requests a production deploy | Ben's avatar gets a bell |
| 1:35 | Approve from the Approvals queue | Aman turns green, deployment continues |
| 1:55 | Switch to 100×, fast-forward one week | progress overlay → summary card |
| 2:15 | Incidents → Nikhil, risk 84 | three plain-language factors, never a label |
| 2:35 | Policy Lab: intern model-downgrade draft | 21% projected savings, 3 legitimate blocks |
| 2:50 | CEO view | spend, waste prevented, blocked, approvals |
| 3:00 | Close on the one-liner | *"This isn't a scripted dashboard. It's a digital enterprise generating exactly the telemetry AgentShield would receive from real coding agents — and the same gates are already listening on an HTTP endpoint for the real ones."* |

```bash
make demo          # runs the scenario end to end, unattended, no errors
git commit -am "feat(phase-9): policy lab, exec view, aws adapters, demo scenario"
git tag v1.0.0
```

---

## Git Strategy

One commit per phase minimum, conventional-commit prefixes, and a tag at the end.

```
chore: init
feat(phase-0): ports, adapters, container, contract tests
feat(phase-1): domain models, single-table store, telemetry emitter
feat(phase-2): policy DSL, gate 1, gate 2, approvals
feat(phase-3): agent runner, 8 tools, sandbox, mock + ollama adapters
feat(phase-4): personas, task generator, tick loop, scenarios
feat(phase-5): REST API, WebSocket, live-mode ingest
feat(phase-6): console — live feed, approvals, control center
feat(phase-7): risk engine, incidents, evaluation harness
feat(phase-8): isometric office view
feat(phase-9): policy lab, exec view, aws adapters, demo scenario
```

Never commit with failing contract tests or a failing architecture guard. Those two suites are the project's structural integrity; a red commit there compounds.

---

## Testing Strategy

| Layer | What | Runs |
|---|---|---|
| Contract | all 8 ports × 2 adapter sets | every phase |
| Architecture | the four greps from `DESIGN.md §3.1` | every phase |
| Unit | DSL, precedence, redaction, gates, budget, approvals, features, scoring, sandbox | per phase |
| Determinism | same seed → identical stream hash | Phase 4 onward |
| Label isolation | features identical with all `GT#` items deleted | Phase 1 and Phase 7 |
| Mode parity | one fixture through sim and `/ingest`, identical decisions | Phase 5 onward |
| Performance | gate p95, 7-day advance, feed throughput, office fps | Phases 2, 4, 6, 8 |
| E2E | seed → advance → approve → evaluate, scripted | Phase 9 |

```bash
make test           # everything
make test-contract  # ports only — the fast pre-commit check
```

---

## Deployment Checklist

- [ ] `AGENTSHIELD_ENV=aws` and every AWS variable set in App Runner configuration
- [ ] Bedrock model access **approved** in the target region (this takes hours sometimes — request it on day 1, not day 4)
- [ ] IAM role scoped to one table, one bucket prefix, one bus, two model ARNs
- [ ] DynamoDB on-demand billing; PITR enabled; TTL attribute configured
- [ ] S3 bucket: block all public access, SSE-S3, lifecycle rule expiring `raw/` after 30 days
- [ ] `CORS_ORIGINS` set to the deployed web origin — no wildcard
- [ ] `INGEST_TOKENS` moved to Secrets Manager, not an environment variable
- [ ] Frontend built with production `VITE_API_BASE` / `VITE_WS_URL`, and the WS URL is `wss://`
- [ ] CloudWatch dashboard: event rate, gate latency, blocked count, spend, Bedrock throttles
- [ ] Alarm on Bedrock throttling and on 5xx rate
- [ ] `/healthz` and `/readyz` wired to the App Runner health check
- [ ] Run `make demo` once against the deployed stack before demo day
- [ ] **Record the demo locally as a backup video.** Conference wifi has ended better projects than this one.

---

## Common Failure Points

| Symptom | Likely cause | Fix |
|---|---|---|
| `repro-check` fails | module-level `random`, `set` iteration, or dict ordering in a seeded path | route every draw through `random.Random(seed_for(...))`; sort before iterating |
| Contract test passes local, fails aws | using a SQLite-only capability (LIKE on the wrong side, implicit ordering) | restrict the adapter to `begins_with` / `between`; re-read `05 §3.2` |
| Events arrive out of order in the UI | using wall time instead of `seq` for ordering | order by `seq` everywhere; `sim_ts` is for display only |
| Approvals never resolve | TTL sweep isn't running, or the sweep runs off wall time | sweep on every tick using `clock.sim_ts` |
| Office badges lag seconds behind | per-avatar store subscriptions, or no event budget in the pump | one subscription, one pump, 12 events/frame (`07 §8`) |
| Avatars render behind desks | depth from world `y` instead of `(tx+ty)` | use `depthFor()` from `07 §2` |
| Risk scores all 50-ish | everyone still `low_confidence` | run `make seed-history`; the baseline needs 20 sessions/person |
| Detector recall ≈ 1.0 | label leakage | run `tests/test_no_label_leakage.py`; check for a `scenario_profile` field crossing into features |
| Detector recall ≈ 0 | adversarial ladder too subtle, or trained on a window that excludes the escalation | widen the window; verify stage events actually emitted |
| Gate latency spikes | policy cache invalidating per call | cache by `(gate, version_hash)`, invalidate only on write |
| Bedrock `AccessDeniedException` | model access not granted in the region | request access in the Bedrock console; it is per-account, per-region |
| Bedrock `ValidationException` on tools | Converse tool schema shape wrong | tools go under `toolConfig.tools[].toolSpec` — see `02-TRD.md §5.3` |
| WS floods the browser at 10× | no coalescing | batch server-side at 250 ms and cap the client queue at 400 |
| Fast-forward takes minutes | a real LLM is being invoked during `advance` | force `MockLLM` inside `advance` regardless of `LLM_PROVIDER` |
| Frontend types drift from the API | hand-written types | regenerate from `packages/contracts/` and commit the output |
