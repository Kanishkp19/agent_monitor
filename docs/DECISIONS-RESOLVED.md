# AgentShield — Resolved Contract Conflicts

> The eleven specification documents contradict each other in seven places, all of them in load-bearing layers. This file is the tie-breaker. When a doc and this file disagree, **this file wins**, and the ruling names which doc was demoted and why.
>
> Established before any code was written. Resolved: 2026-09-18.

---

## C1 — How many event types are there?

**Conflict.** `DESIGN.md §9.2` says "the 14 event types" and then lists fifteen. `05-BACKEND-SCHEMA.md §5` gives payload schemas for the same fifteen. Three more are referenced elsewhere but appear in neither list: `audit.raw_access` (`DESIGN.md §5.3`, `02-TRD.md §8`), `sim.meeting.started` and `sim.meeting.ended` (`07-OFFICE-SIMULATION.md §7.2`). And `05 §6.10` tells `/ingest/events` to reject "any `detail_type` outside the 14 known types".

**Ruling.** `packages/contracts/events.schema.json` is the **sole** source of truth for event types. The count is whatever the schema holds — currently **18**:

| # | Type | Emitted by |
|---|---|---|
| 1 | `sim.tick` | `sim/engine.py` |
| 2 | `sim.day.completed` | `sim/engine.py` |
| 3 | `sim.meeting.started` | `sim/scenarios.py` |
| 4 | `sim.meeting.ended` | `sim/scenarios.py` |
| 5 | `task.requested` | `sim/engine.py`, `/ingest/gate1` |
| 6 | `gate1.decision` | `governance/gate1.py` caller |
| 7 | `model.invoked` | `agent/runner.py` |
| 8 | `action.requested` | `agent/runner.py` |
| 9 | `gate2.decision` | `governance/gate2.py` caller |
| 10 | `approval.requested` | `governance/approvals.py` |
| 11 | `approval.decided` | `governance/approvals.py` |
| 12 | `sandbox.executed` | `sandbox/` |
| 13 | `action.blocked` | `agent/runner.py` |
| 14 | `task.completed` | `agent/runner.py` |
| 15 | `budget.exceeded` | `governance/budget.py` caller |
| 16 | `risk.updated` | `risk/scoring.py` caller |
| 17 | `incident.opened` | `risk/incidents.py` |
| 18 | `audit.raw_access` | blob-store reads of `raw/{task_id}/prompt.json` |

**Consequences.**
- No literal `14` appears anywhere in code or prose. `/ingest/events` validates against the schema registry loaded from `events.schema.json`, not against a hardcoded list.
- Adding an event type means editing the schema and re-running `packages/contracts/generate.py`. Both the Pydantic models and the TypeScript types fall out of it.
- `telemetry.degraded` is **not** an event. `DESIGN.md §12` describes it as a UI banner flag; it stays a flag on the health payload.

---

## C2 — How many archetypes, and how many of each?

**Conflict.** `02-TRD.md §3.1` defines `Archetype` with **six** values: `intern`, `engineer`, `senior_engineer`, `manager`, `devops`, `exec`. `DESIGN.md §7.3` presents a table with **seven** rows (splitting `senior_manager` and `ceo` out), whose count column sums to **19**, and which gives `engineer: 6`. `05-BACKEND-SCHEMA.md §10.2` seeds **20** named employees, of whom **8** are engineers.

**Ruling.** The **`05 §10.2` seed table** and the **six-value `Archetype` enum** are authoritative.

- `senior_manager` and `ceo` are **roles** (`Role` enum), not archetypes. Their archetypes are `manager` and `exec` respectively.
- `DESIGN.md §7.3`'s count column is illustrative prose describing behavioural tuning, not a seed specification. Its per-archetype *attributes* (token norm, budget, mistake probability, prod access) remain authoritative — only the counts are demoted.

**Resulting distribution**, derived from the seed table:

| Archetype | Count | Employees |
|---|---|---|
| `exec` | 1 | emp_001 |
| `manager` | 2 | emp_002 (senior_manager), emp_003 (manager) |
| `senior_engineer` | 3 | emp_004, emp_005, emp_006 |
| `engineer` | 8 | emp_007–emp_012, emp_017, emp_020 |
| `intern` | 5 | emp_013–emp_016, emp_018 |
| `devops` | 1 | emp_019 |
| **Total** | **20** | |

Scenario overlays, applied on top and never visible to `risk/`: `emp_017` = `adversarial`, `emp_014` = `sloppy`, all others `normal`.

This satisfies the Definition of Done line "20 employees, 6 archetypes, exactly 1 hidden adversarial profile".

---

## C3 — Where does the blob store write?

**Conflict.** `README.md §3` says `./var/blobs`. `DESIGN.md §3.2` and the `.env.example` in `02-TRD.md §4` say `./.data/blobs`.

**Ruling.** **`./.data/blobs`.** The `.env.example` block is the build sheet and is copied verbatim into the repo; `README.md`'s mention is prose. Everything runtime-generated lives under `.data/` (SQLite database, blobs, dead-letter file), which is a single `.gitignore` entry.

---

## C4 — SAM or CDK?

**Conflict.** `00-MASTER-PROMPT.md` and `DESIGN.md §3.5` use AWS SAM at `infra/aws/template.yaml`, and `06-IMPLEMENTATION-PLAN.md §9c` runs `sam deploy -t infra/aws/template.yaml`. `README.md §3` shows an `infra/cdk/` directory.

**Ruling.** **SAM**, at `infra/aws/template.yaml`. Two of three docs and every actual deploy command agree. `infra/cdk/` is not created.

---

## C5 — Where do the contract tests live?

**Conflict.** `00-MASTER-PROMPT.md` places them at `services/api/tests/contract/`. `README.md §3` shows `infra/tests/contract/`.

**Ruling.** **`services/api/tests/contract/`.** They import the adapters directly and run under the API's virtualenv; putting them in `infra/` would need a second environment for no benefit.

---

## C6 — Who is allowed to read `AGENTSHIELD_ENV`?

**Conflict.** `00-MASTER-PROMPT.md` (agent rule 2, and the Definition of Done grep) says `container.py` is the only file that may read it. `DESIGN.md §3.1`'s guard excludes both `container.py` **and** `config.py`.

**Ruling.** Split the two concerns, because they are genuinely different:

- **`config.py` reads it** — `Settings(BaseSettings)` must load `AGENTSHIELD_ENV` into a typed `env: Literal["local", "aws"]` field like any other setting. This is loading, not branching.
- **`container.py` is the only file that branches on it** — the single `if settings.env == "aws":` in the codebase.

`tests/test_architecture.py` asserts both halves separately: the string `AGENTSHIELD_ENV` appears only in `config.py`, and a comparison against `settings.env` appears only in `container.py`.

---

## C7 — Is the contract generated from Pydantic, or from JSON Schema?

**Conflict.** `README.md §3` describes `packages/contracts/` as "shared TypeScript types, generated from Pydantic". `00-MASTER-PROMPT.md` names `events.schema.json` as "source of truth for event shapes", with `generate.py` producing "TS types + Pydantic models".

**Ruling.** **JSON Schema is the source.** `packages/contracts/events.schema.json` is hand-maintained; `generate.py` emits both the Pydantic payload models and `apps/web/src/types/generated.ts`. Neither output is hand-written or hand-edited.

Generating Python *from* Python would leave the TypeScript a second-class derivative and make the schema file decorative. Generating both from one neutral schema keeps them provably in step, and the schema doubles as the runtime validator for `/ingest/events` (see C1).

**Consequence.** Generated files are committed to the repository, so a clean clone type-checks without running the generator. CI re-runs the generator and fails if the output differs.
