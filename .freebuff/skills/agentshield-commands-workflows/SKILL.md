---
name: agentshield-commands-workflows
description: Use whenever you need to run, seed, test, inspect, or build AgentShield. Maps every task to the project's own tasks.py commands (never raw make/pytest/npm assumptions) and lists what each verification gate protects.
alwaysApply: true
---

# AgentShield commands & workflows

`tasks.py` (repo root, stdlib-only) replaces the docs' Makefile one-for-one. The backend
venv lives at `services/api/.venv` (Python ≥ 3.11 required — `StrEnum`). Always go through
`python tasks.py <target>`; don't hand-roll uvicorn/pytest/npm invocations.

## Daily loop

```bash
python tasks.py setup          # venv + pip + npm install + .env from .env.example (first time)
python tasks.py seed           # run: 20 employees, 6 repos, 13 policies (deterministic from seed)
python tasks.py seed-history   # +14 sim-days so risk baselines exist (else everything is low_confidence)
python tasks.py dev            # API :8000 + web :5173 together
```

Open http://localhost:5173 — you land in the office. Default `LLM_PROVIDER=mock` runs fully
offline. Real models: `LLM_PROVIDER=ollama` (local) or `bedrock` (AWS creds needed).

## Verification gates (run the relevant one before declaring done)

| Command | Protects |
|---|---|
| `python tasks.py check` | Everything CI runs: api lint+mypy(strict on domain/ports/governance/risk)+tests, web lint+test+build |
| `python tasks.py test-contract` | Port contract suites against BOTH adapter sets (local + moto); **skips fail** |
| `python tasks.py test` / `test-web` | Backend unit/e2e · vitest (office isolation test included) |
| `python tasks.py lint` / `typecheck` | ruff check+format · mypy strict layers |
| `python tasks.py check-secrets` | No raw canary secret in storage — MUST stay zero |
| `python tasks.py repro-check` | Same seed ⇒ byte-identical event stream (determinism) |
| `python tasks.py build` | Zero TS errors production build |

## Simulation control & inspection

```bash
python tasks.py advance --days 7      # headless fast-forward (forces MockLLM)
python tasks.py demo                  # unattended deterministic demo, prints risk table + incidents
python tasks.py train-risk            # fit IsolationForest on session vectors
python tasks.py evaluate              # detection metrics vs ground truth (recall/FP/ttd)
python tasks.py export-dataset        # .data/export/{sessions,events,labels}.parquet + DATASET-CARD.md
python tasks.py inspect-events [--run-id R] [--limit N]
python tasks.py run-task --employee emp_013 --task "Fix payment API error" [--repo payments-api] [--env production]
python tasks.py gate-repl             # probe gate decisions interactively
python tasks.py contracts             # regenerate Pydantic + TS types from events.schema.json
```

Infra helpers (no tasks.py target): `python infra/scripts/ws_tail.py --run-id <run>` and
`python infra/scripts/reference_client.py --run-id <run>` (Live Mode walkthrough).
Art assets: `python tasks.py atlas` (placeholder) — real art drops in by replacing PNGs.

## Data locations

- SQLite store: `.data/agentshield.db` (single `items` table) · blobs: `.data/blobs/`
- Dead-letter telemetry: `.data/dead-letter.jsonl` (emitter sets `degraded` → UI banner)
- Datasets: `.data/export/` · Reset: `python tasks.py clean` (never touches source)

## Ports and collision etiquette

API 8000, web 5173 (`tasks.py dev`). If a port is busy, another thread may be running a
server — check listeners before starting a second one; never kill processes you didn't
start. Health: `GET /healthz` (names each adapter — verifies which env you're on) and
`GET /readyz` (docstore answers + policies armed).

## Env essentials (root `.env`; see `.env.example`)

`AGENTSHIELD_ENV=local|aws` · `LLM_PROVIDER=mock|ollama|bedrock` · `SIM_SEED`,
`SIM_LLM_INVOCATION_RATE` · `RISK_*` weights/thresholds · `INGEST_TOKENS=token:actor_id,...`
(Live Mode identity) · AWS names (table/bucket/bus) only matter when env=aws.
