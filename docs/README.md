# AgentShield

**A governance and observability control plane for AI coding agents — with a 2D isometric office digital twin on top of it.**

AgentShield sits between your AI agents and everything they touch. Every model call passes **Gate 1 (request governance)**. Every tool call passes **Gate 2 (action governance)**. Each gate returns one of four decisions — `allow`, `redact`, `review`, `block` — and every decision emits a telemetry event.

The same core runs in two modes:

```
                    AGENTSHIELD CORE
        (policies · gates · risk engine · telemetry)
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
   SIMULATION MODE                    LIVE MODE
   20 virtual employees          Claude Code, Codex,
   in a 2D pixel office          MCP agents, IDE agents
```

Simulation Mode is not a toy. It is the synthetic dataset generator, the policy what-if environment, the evaluation harness for the anomaly detector, and the demo. Live Mode ingests the exact same event envelope from real agents through `/ingest/*`. Neither mode has its own copy of the rules.

---

## 1. What makes this different from a dashboard

| | |
|---|---|
| **Two gates, not one** | Governance happens before the model call *and* before every tool call. Blocking a bad prompt is easy; blocking `read .env.production` mid-session is the actual problem. |
| **Fail closed** | If the policy engine errors, the decision is `block`. Never `allow`. |
| **Hidden ground truth** | One of the 20 seeded employees (`emp_017`) is adversarial. That label lives in a separate key space the risk engine physically cannot read. It is used only by `infra/scripts/evaluate.py`, after the fact, to score detection. |
| **Policy what-if** | Run a proposed rule against 100 simulated days before enforcing it on humans. Get requests affected, savings, legitimate work blocked, extra approvals/day. |
| **Local-first, AWS-ready** | The whole thing runs on a laptop with no AWS account. Flipping to AWS is one environment variable, not a rewrite. See §4. |

---

## 2. Quickstart (no AWS account, no API keys)

**Prerequisites:** Python 3.11+, Node 20+, `make`, `git`.

```bash
git clone <your-repo> agentshield && cd agentshield

make setup          # venv + pip install + pnpm install + .env from .env.example
make seed           # seeds Acme Payments: 4 teams, 6 repos, 20 employees, 12 policies
make seed-history   # generates ~30 simulated days of telemetry so charts aren't empty
make dev            # API on :8000, web on :5173
```

Open **http://localhost:5173**. You land in the office. Press `▶ REAL TIME` and characters start working.

With the default `LLM_PROVIDER=mock`, the deterministic agent replays scripted-but-realistic tool sequences. Everything — gates, approvals, risk scoring, telemetry, the office, the exec view — works. Nothing calls out to the internet.

**To use a real model**, set one of:

```bash
LLM_PROVIDER=bedrock    # AWS credentials via the usual chain
LLM_PROVIDER=ollama     # OLLAMA_MODEL=qwen2.5-coder:7b — runs on an M-series Mac
```

Only sessions flagged as *interesting* invoke a real model (`llm_invocation_rate=0.08`, max 4 concurrent). The other 19 employees stay cheap state machines. This is deliberate — see `DESIGN.md §7`.

### The scripted demo

```bash
make demo
```

Runs the three-minute beat sheet: secret-access block → cost anomaly → approval round-trip → 100× week fast-forward → exec view. Beat-by-beat script is in `06-IMPLEMENTATION-PLAN.md §11`.

---

## 3. Repository layout

```
agentshield/
├── services/api/          FastAPI backend
│   ├── core/              gates, policy engine, risk engine, approvals
│   ├── sim/               clock, persona engine, task generator, FSMs
│   ├── ports/             8 port Protocols — the portability contract
│   ├── adapters/
│   │   ├── local/         SQLite, filesystem, in-proc bus, asyncio queue
│   │   └── aws/           DynamoDB, S3, EventBridge, SQS, CloudWatch, Bedrock
│   ├── api/               REST routers + WebSocket
│   └── container.py       the ONLY file that reads AGENTSHIELD_ENV
├── apps/web/              Vite + React 19 + Tailwind v4
│   ├── src/scenes/        Phaser: BootScene, OfficeScene, HudScene
│   ├── src/components/    console UI, drawers, tables, charts
│   └── src/lib/bridge.ts  event pump: telemetry → canvas
├── packages/contracts/    shared TypeScript types, generated from Pydantic
└── infra/
    ├── scripts/           seed.py, evaluate.py, fast_forward.py
    ├── cdk/               AWS stack
    └── tests/contract/    same suite run against local AND aws adapters
```

---

## 4. The local → AWS switch

This is the constraint the whole design is bent around, so it is worth being precise about how it works.

Eight ports define everything that touches the outside world:

`LLMPort` · `DocStorePort` · `BlobStorePort` · `EventBusPort` · `MetricsPort` · `QueuePort` · `SecretsPort` · `ClockPort`

Each has two adapter implementations. `container.py` picks a set:

```bash
AGENTSHIELD_ENV=local   # SQLite, ./var/blobs, asyncio bus, mock/ollama LLM
AGENTSHIELD_ENV=aws     # DynamoDB, S3, EventBridge, SQS, CloudWatch, Bedrock
```

No other file in the codebase reads that variable. No `import boto3` exists outside `adapters/aws/`. Four grep guards in CI enforce this (`DESIGN.md §3`).

The trick that makes it painless: **abstract the transport, adopt the model.** The local SQLite store is not a relational schema — it is a single `items(pk, sk, gsi1pk, gsi1sk, gsi2pk, gsi2sk, body, ttl)` table with no joins and no scans, ever. All 25 access patterns (A1–A25 in `05-BACKEND-SCHEMA.md §3.2`) are written as key lookups. So the DynamoDB migration is a driver swap, not a data-model redesign.

The contract test suite runs identically against both adapter sets — `moto` for the AWS side, so you can verify AWS behaviour with no account:

```bash
make test-contract
```

Deploy path, when you're ready: `make deploy` → CDK stack → set `AGENTSHIELD_ENV=aws`. Request Bedrock model access on day one; approval is not instant.

---

## 5. Documentation index

Read in this order. Each doc assumes the ones above it.

| File | What it's for |
|---|---|
| **[`architecture.md`](./architecture.md)** | **Plain-English architecture.** Every layer, flow and invariant explained with diagrams — office bots, Sandbox, agent integration, risk engine. Start here if the spec docs feel heavy. |
| **[`GUIDE.md`](./GUIDE.md)** | **Operating manual.** Run it, drive the office, use the Sandbox, change rules, integrate Claude Code/Codex/MCP, and test everything — with expected outputs. |
| **[`09-AGENT-INTEGRATION.md`](./09-AGENT-INTEGRATION.md)** | Connecting real coding agents: the universal hook, MCP `agentshield_gate`, Claude Code hooks, Codex config, the 8-tool mapping. |
| **[`graph/GRAPH.md`](./graph/GRAPH.md)** | **The codebase map (graphify).** Layer diagram, both data-flow walkthroughs, the 12 invariants with their enforcement, node index, key layout. Machine-readable twin: [`graph/graph.json`](./graph/graph.json). Start here if you are an agent — or a human who wants the whole shape in ten minutes. |
| **`00-MASTER-PROMPT.md`** | **Start here.** Project summary, hard constraints, tech stack, full folder tree, 12 agent operating rules, build order, Definition of Done. This is the file you paste into your coding agent. |
| `01-PRD.md` | Personas, features F1–F12 with acceptance criteria, 20 user stories, non-goals, success metrics. |
| `DESIGN.md` | System architecture. The portability contract, both gate algorithms, the simulation engine, risk maths, label isolation, decisions log D1–D10. |
| `02-TRD.md` | Pinned versions, every enum and type, port protocols, `.env.example`, key code patterns, error model, performance targets. |
| `05-BACKEND-SCHEMA.md` | Single-table key design, access patterns A1–A25, all 14 event schemas, full REST contract, policy DSL, seed data. |
| `03-APP-FLOW.md` | All 11 routes, navigation, and a screen-by-screen spec. |
| `04-UI-UX-BRIEF.md` | Design tokens, typography, the component library, motion, accessibility, full `globals.css`. |
| `07-OFFICE-SIMULATION.md` | The 2D office. Isometric maths, floor plan, assets and licensing, scenes, avatar FSM, the event pump, performance budget, V0–V8 build order. |
| `06-IMPLEMENTATION-PLAN.md` | Phases 0–9 with entry/exit criteria, exact commands, verification blocks, debugging table, demo script. |

---

## 6. Tech stack

**Backend** — Python 3.11, FastAPI 0.115, Pydantic v2, SQLite (local) / DynamoDB (AWS), scikit-learn (IsolationForest), boto3, asyncio tick loop.

**Frontend** — Vite 6, React 19, TypeScript (strict), Tailwind v4 CSS-first `@theme`, Phaser 3.90 for the office canvas, Recharts for the exec view.

**Why not Next.js:** no SSR benefit here, and Phaser is happier in a plain SPA. Why not 20 live LLM agents: cost, latency, and non-determinism during a demo. Both justified in `DESIGN.md §14`.

---

## 7. Two rules that decide whether this ships

1. **Do not build a game instead of AgentShield.** The office is a *renderer over telemetry*. It holds no authoritative state. If the canvas and the API disagree, the API is right. The card-grid fallback (`AvatarGrid.tsx`) is built **first** and stays working forever — if Phaser eats your Tuesday, you ship the grid and the project is still complete.
2. **The cut line is V5.** `07-OFFICE-SIMULATION.md §13` orders the office work V0→V8. Everything from V6 up is polish. Cut without regret.

---

## 8. Handing this to someone else

A judge or teammate needs three things:

```bash
make setup && make seed && make seed-history && make dev
```

…then `make demo`, and `00-MASTER-PROMPT.md` open next to it. No AWS account, no keys, no external services. If the laptop has network trouble on the day, there is a recorded backup video — recording it is a checklist item in `06-IMPLEMENTATION-PLAN.md`, not an afterthought.

---

## 9. Licensing note on art assets

The default sprite pack is **Kenney (CC0)** so the repo is clean out of the box. The isometric packs that look closest to the reference screenshot (LimeZu and similar itch.io packs) are **paid licences** — buy them if you want that exact look, and record attribution in `CREDITS.md`. `infra/scripts/make_placeholder_atlas.py` generates a working flat-colour atlas so development is never blocked on art.
