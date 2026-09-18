# AgentShield — Master Agent Prompt

> **Read this file completely before writing a single line of code.** Then load the other documents in the order listed below. Do not invent architecture that is not in these docs. If something seems missing, search the docs again — it is almost certainly specified.

---

## What We're Building

**AgentShield** is a governance and observability control plane for AI coding agents. It sits between a human's request and the model, and again between the agent and its tools, making four possible decisions at each point: **allow, redact, review, block**. Everything it governs — requests, tool calls, tokens, cost, approvals, risk — becomes telemetry that feeds a behavioural risk engine.

The product ships in two modes that share one governance core:

- **Simulation Mode** — a 20-employee virtual software company runs inside the browser as a 2D isometric pixel-art office. Employees request work, agents use models, agents attempt tool calls, managers approve things. One employee is secretly adversarial. AgentShield must discover that from telemetry alone.
- **Live Mode** — the same gates, policies and risk engine receive events from real agents (Claude Code, Codex, MCP agents, IDE agents) over an HTTP ingest API. **Nothing in the governance core changes between modes.**

The simulation is not a toy demo layer. It is the synthetic data generator, the policy test-bench, the ML evaluation harness and the demo, all at once.

---

## The Two Hard Constraints (these shape every decision)

### 1. Local-first, AWS-later — with zero rewrite

The entire system must run on a laptop with `make dev` and **no AWS account, no credentials, no network**. Flipping one environment variable (`AGENTSHIELD_ENV=local → aws`) must move it onto Bedrock, DynamoDB, S3, EventBridge and CloudWatch **without touching a single line of domain, simulation, governance, risk or UI code**.

This is achieved with a strict ports-and-adapters boundary. See `DESIGN.md → Section 3: The Portability Contract`. The rules:

- Domain code imports **only** from `agentshield/ports/`. Never `boto3`. Never `sqlite3`. Never `requests`.
- `agentshield/container.py` is the **only** file in the entire backend allowed to read `AGENTSHIELD_ENV` or to import from `adapters/`.
- The local document store is a **DynamoDB-shaped key-value store in SQLite** (same PK/SK/GSI access patterns). Not an ORM. Not relational joins. This is deliberate — see `05-BACKEND-SCHEMA.md → Section 2`.
- Every port has exactly two implementations and a shared contract test suite that both must pass (`services/api/tests/contract/`).

### 2. Don't build a game instead of building AgentShield

The office view is a *renderer over the telemetry stream*. It has no authority, no state of its own, and no gameplay. If the browser tab closes, the simulation keeps running server-side and the office rehydrates from a snapshot. Budget for it: **one day maximum**, and only after the gates work.

Build order is therefore: **gates → agent → telemetry → dashboards → office**. Not the reverse.

---

## Tech Stack (Non-Negotiable)

| Layer | Choice | Why this and not the default |
|---|---|---|
| Backend | **Python 3.11 + FastAPI 0.115 + Pydantic v2** | The risk engine needs scikit-learn; `boto3` is first-class; async loop drives the simulation tick |
| Sim/agent runtime | **asyncio task group inside the FastAPI process** | No broker needed for a 4-day build; swaps to SQS + workers via `QueuePort` |
| Frontend | **Vite 6 + React 19 + TypeScript strict** | Phaser needs a plain SPA; the backend is FastAPI, so Next.js would add a second unused backend |
| Styling | **Tailwind CSS v4** (CSS-first `@theme`) + hand-built components | Full token control; see `04-UI-UX-BRIEF.md` |
| Office renderer | **Phaser 3.90** (Canvas/WebGL) | Sprite batching, tilemaps, tweens, camera — do not write a game engine |
| Client state | **Zustand 5** (sim + telemetry stores) + **TanStack Query 5** (REST) | WebSocket pushes into Zustand; REST reads cached by TanStack |
| Charts | **Recharts 2** | Exec dashboard only |
| Icons | **lucide-react** | Chrome only — the office uses sprites |
| Local store | **SQLite (aiosqlite)** in single-table KV mode | Mirrors DynamoDB access patterns exactly |
| Local LLM | **Ollama** (`qwen2.5-coder:7b`) or `MockLLM` | Runs on 16 GB Apple Silicon; `MockLLM` needs no model at all |
| Local bus | **asyncio pub/sub + SQLite outbox** | Mirrors EventBridge envelope shape |
| AWS targets | **Bedrock, DynamoDB, S3, EventBridge, CloudWatch EMF, Secrets Manager, SQS** | Swapped in by `container.py` |
| ML | **scikit-learn 1.5** — IsolationForest + rolling z-scores | Unsupervised; never sees ground-truth labels |
| Tests | **pytest + pytest-asyncio**, **Vitest** | Contract tests are mandatory, not optional |

---

## Project Folder Structure (Scaffold This Exactly)

```
agentshield/
├── Makefile                          # dev, seed, test, demo, aws-deploy
├── .env.example
├── docker-compose.yml                # api + web + ollama (optional profile)
├── docs/                             # these 10 documents
│
├── services/api/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── agentshield/
│       ├── main.py                   # FastAPI app, lifespan, WS, CORS
│       ├── config.py                 # Settings (pydantic-settings)
│       ├── container.py              # ◄ ONLY file that reads AGENTSHIELD_ENV
│       ├── deps.py                   # FastAPI dependency providers
│       │
│       ├── domain/
│       │   ├── enums.py              # Decision, TaskStatus, Role, Environment, ToolName
│       │   ├── models.py             # Employee, Task, GateRequest, AgentAction, Approval, Policy, Incident
│       │   ├── events.py             # EventEnvelope + all 14 event payload models
│       │   └── errors.py
│       │
│       ├── ports/                    # ◄ abstract interfaces only, zero vendor imports
│       │   ├── llm.py                # LLMPort.complete(messages, tools) -> LLMResult
│       │   ├── docstore.py           # DocStorePort.put/get/query/batch_put/update
│       │   ├── blobstore.py          # BlobStorePort.put_object/get_object/presign
│       │   ├── eventbus.py           # EventBusPort.publish(envelope) / subscribe()
│       │   ├── metrics.py            # MetricsPort.count/gauge/timing
│       │   ├── queue.py              # QueuePort.enqueue/dequeue
│       │   ├── secrets.py            # SecretsPort.get
│       │   └── clock.py              # ClockPort.now_sim/now_wall/advance
│       │
│       ├── adapters/
│       │   ├── local/
│       │   │   ├── sqlite_docstore.py
│       │   │   ├── fs_blobstore.py
│       │   │   ├── memory_eventbus.py      # + SQLite outbox table
│       │   │   ├── ollama_llm.py
│       │   │   ├── mock_llm.py             # seeded deterministic tool-call scripts
│       │   │   ├── stdout_metrics.py
│       │   │   ├── asyncio_queue.py
│       │   │   └── dotenv_secrets.py
│       │   └── aws/
│       │       ├── dynamo_docstore.py
│       │       ├── s3_blobstore.py
│       │       ├── eventbridge_bus.py
│       │       ├── bedrock_llm.py
│       │       ├── cloudwatch_metrics.py   # EMF structured logs
│       │       ├── sqs_queue.py
│       │       └── secretsmanager_secrets.py
│       │
│       ├── sim/
│       │   ├── engine.py             # tick loop, speed control, concurrency cap
│       │   ├── persona.py            # 6 archetypes + adversarial overlay
│       │   ├── task_generator.py     # seeded task sampling per persona
│       │   ├── scenarios.py          # scripted demo injections (demo.yaml loader)
│       │   ├── seed.py               # 20 employees, repos, resources, policies
│       │   └── snapshot.py           # office state snapshot for rehydration
│       │
│       ├── governance/
│       │   ├── policy_engine.py      # match + precedence resolution
│       │   ├── dsl.py                # JSON condition evaluator
│       │   ├── gate1.py              # request governance
│       │   ├── gate2.py              # action governance
│       │   ├── redaction.py          # secret detectors + masking
│       │   ├── budget.py             # per-employee/team/day spend guards
│       │   └── approvals.py          # approval lifecycle + TTL expiry
│       │
│       ├── agent/
│       │   ├── runner.py             # tool-use loop, max 8 iterations
│       │   ├── tools.py              # 8 tool definitions (JSON schema)
│       │   ├── router.py             # model selection by task complexity + policy
│       │   └── prompts.py
│       │
│       ├── sandbox/
│       │   ├── vfs.py                # virtual repo filesystem (in DocStore)
│       │   ├── git_ops.py
│       │   ├── test_runner.py        # simulated pass/fail
│       │   └── deploy.py             # simulated deploy to staging/production
│       │
│       ├── risk/
│       │   ├── features.py           # 12-feature session vector
│       │   ├── baseline.py           # rolling per-employee stats
│       │   ├── scoring.py            # composite 0–100
│       │   ├── isolation.py          # IsolationForest train/score
│       │   └── incidents.py          # incident open/merge/close
│       │
│       ├── telemetry/
│       │   ├── emitter.py            # single choke point: every event goes here
│       │   ├── replay.py             # event replay for policy lab
│       │   └── export.py             # dataset export to Parquet/CSV
│       │
│       └── api/
│           ├── routes_sim.py
│           ├── routes_employees.py
│           ├── routes_tasks.py
│           ├── routes_events.py
│           ├── routes_approvals.py
│           ├── routes_policies.py
│           ├── routes_policy_lab.py
│           ├── routes_risk.py
│           ├── routes_metrics.py
│           ├── routes_ingest.py      # ◄ Live Mode entry point
│           └── ws.py
│
├── services/api/tests/
│   ├── contract/                     # run against BOTH adapter sets
│   │   ├── test_docstore_contract.py
│   │   ├── test_eventbus_contract.py
│   │   ├── test_blobstore_contract.py
│   │   └── test_llm_contract.py
│   ├── unit/
│   └── e2e/test_demo_scenario.py
│
├── apps/web/
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   ├── public/assets/office/         # tileset.png, characters.png, office-map.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx                   # router + AppShell
│       ├── routes/
│       │   ├── office.tsx
│       │   ├── live.tsx
│       │   ├── approvals.tsx
│       │   └── control/{index,policies,policy-lab,employees,costs,risk,incidents}.tsx
│       ├── game/
│       │   ├── PhaserGame.tsx        # React ⇄ Phaser mount boundary
│       │   ├── config.ts
│       │   ├── scenes/{BootScene,OfficeScene,HudScene}.ts
│       │   ├── entities/{Avatar,StatusBadge,SpeechBubble,DeskZone}.ts
│       │   ├── systems/{Pathfinder,AvatarFSM,EventQueue,CameraRig}.ts
│       │   └── bridge.ts             # Zustand → Phaser event pump
│       ├── components/               # see 04-UI-UX-BRIEF.md
│       ├── stores/{simStore,telemetryStore,uiStore}.ts
│       ├── lib/{api,ws,format,risk}.ts
│       ├── types/index.ts            # generated from packages/contracts
│       └── styles/globals.css
│
├── packages/contracts/
│   ├── events.schema.json            # source of truth for event shapes
│   └── generate.py                   # → TS types + Pydantic models
│
└── infra/
    ├── aws/template.yaml             # SAM: DynamoDB, S3, EventBridge, App Runner, IAM
    ├── aws/eventbridge-rules.yaml
    └── scripts/{seed_local.py,export_dataset.py,migrate_local_to_aws.py}
```

---

## Documents to Load (In Order)

| # | File | What it gives you |
|---|---|---|
| 1 | `01-PRD.md` | Features, personas, acceptance criteria, what is explicitly out of scope |
| 2 | `DESIGN.md` | System architecture, the ports contract, gate algorithms, risk maths, local→AWS migration |
| 3 | `02-TRD.md` | Package versions, all TypeScript/Pydantic types, env vars, error handling, security |
| 4 | `05-BACKEND-SCHEMA.md` | Single-table data model, every access pattern, full REST + WS contract, Pydantic validators |
| 5 | `03-APP-FLOW.md` | Every route, every screen, every loading/empty/error state, every modal |
| 6 | `04-UI-UX-BRIEF.md` | Tokens, exact Tailwind class strings, component states, animation timings |
| 7 | `07-OFFICE-SIMULATION.md` | The Phaser office: tilemap, sprites, FSM, pathfinding, event pump, asset list |
| 8 | `06-IMPLEMENTATION-PLAN.md` | The 9 phases with atomic tasks and verification commands |
| 9 | `README.md` | What to hand a judge or a teammate |

---

## Agent Operating Rules

1. **Never import `boto3`, `sqlite3`, `httpx`, or `ollama` outside `adapters/`.** If you need one in domain code, you need a port instead.
2. **`container.py` is the only file that branches on environment.** No `if settings.env == "aws"` anywhere else. Grep for it before finishing each phase.
3. **Every event goes through `telemetry/emitter.py`.** No direct writes to the event stream, no direct bus publishes from domain code. One choke point means Live Mode and Simulation Mode are provably identical.
4. **The detector never sees `hidden_ground_truth`.** It is written on a separate item key (`SK = GT#<event_seq>`) that the risk module has no read path to. Evaluation scripts in `infra/scripts/` read it. If you catch yourself passing a label into a feature vector, stop.
5. **Check `05-BACKEND-SCHEMA.md` before writing any persistence call.** Access patterns are enumerated; if yours is not listed, add it to the doc with its GSI first.
6. **Check `04-UI-UX-BRIEF.md` before writing any `className`.** Use the token names, not raw hex.
7. **Every API input is validated by the Pydantic model named in `05-BACKEND-SCHEMA.md`.** Return the documented error envelope — never a bare FastAPI 422 for a business rule.
8. **Every screen implements loading, empty and error states** exactly as written in `03-APP-FLOW.md`. No silent blanks.
9. **The simulation must be reproducible.** Every random draw comes from `run.seed`-derived `random.Random` instances, never module-level `random`. Same seed → byte-identical event stream when `LLM_PROVIDER=mock`.
10. **No `any` in TypeScript, no untyped dicts crossing a module boundary in Python.** Shared shapes come from `packages/contracts/`.
11. **Phaser never calls the API.** It reads from the Zustand store via `bridge.ts` only.
12. **Before finishing a phase, run the phase's verification block** from `06-IMPLEMENTATION-PLAN.md` and paste the output.

---

## Build Order

```
Phase 0  Scaffold + ports + container + contract tests
Phase 1  Domain models, SQLite DocStore, telemetry emitter
Phase 2  Policy engine + Gate 1 + Gate 2 (headless, tested by pytest)
Phase 3  Agent runner + sandbox tools + MockLLM, then Ollama
Phase 4  Simulation engine: personas, task generator, tick loop, speed control
Phase 5  REST + WebSocket API, seed script, demo scenario
Phase 6  Web shell: Live Feed + Approvals + Control Center
Phase 7  Risk engine: baselines, IsolationForest, incidents, evaluation harness
Phase 8  The 2D office (Phaser) — the whole visual layer
Phase 9  Policy Lab, exec view, AWS adapters, deploy, demo recording
```

Phases 0–5 are the product. Phase 8 is the thing people remember. Do not reorder.

---

## Definition of Done

**Portability**
- [ ] `AGENTSHIELD_ENV=local make dev` works with no AWS credentials present and no internet
- [ ] `grep -rn "AGENTSHIELD_ENV" services/api/agentshield/ | grep -v container.py` returns nothing
- [ ] `grep -rn "boto3" services/api/agentshield/ | grep -v adapters/aws` returns nothing
- [ ] Contract tests pass against both `local` and `aws` adapter sets (aws via moto)

**Governance**
- [ ] All 12 seeded policies load and evaluate; precedence `block > review > redact > allow` is unit-tested
- [ ] Gate 1 redacts an injected secret and the raw value never appears in any stored event
- [ ] Gate 2 blocks `read_file(.env.production)` for every role below `devops`
- [ ] An approval request expires after TTL and the task transitions to `denied_timeout`

**Simulation**
- [ ] 20 employees, 6 archetypes, exactly 1 hidden adversarial profile, seeded and reproducible
- [ ] `POST /sim/runs/{id}/advance {sim_days: 7}` completes in under 20 s with `LLM_PROVIDER=mock`
- [ ] Same seed produces an identical event stream hash across two runs
- [ ] At least one task per demo run invokes a real LLM and produces genuine tool calls

**Risk**
- [ ] IsolationForest trains on ≥ 2 000 sessions with zero label leakage
- [ ] Evaluation harness reports precision/recall for the hidden actor, reading ground truth only post-hoc
- [ ] Every risk score has an explanation listing its top 3 contributing features

**Interface**
- [ ] All 11 routes in `03-APP-FLOW.md` render and navigate
- [ ] Office renders 20 avatars at ≥ 50 fps at 1× and 10×; 100× switches to fast-forward summary
- [ ] Clicking any avatar opens the employee drawer with live counters
- [ ] Approving from the Approvals view updates the avatar badge within 500 ms
- [ ] Reloading the page rehydrates the office from `/sim/runs/{id}/state` with no visual desync

**Delivery**
- [ ] `make demo` runs the scripted 3-minute scenario end to end without human input
- [ ] `pytest` green, `npm run build` green with zero TS errors
- [ ] `README.md` quickstart works on a clean machine
