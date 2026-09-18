# AgentShield — Product Requirements Document

> v1 (hackathon MVP) · Owner: Kanishk · Build window: 4 days

## Assumptions

1. **Web only.** Desktop-first, 1440×900 design target. Usable down to 1024px. Not mobile-responsive — this is an ops console and a demo artifact.
2. **No authentication in v1.** A `?role=` query param and a role switcher in the header simulate CEO / Security Admin / Manager / Engineer views. Real auth is v2 (see Non-Goals).
3. **Single organisation, single active simulation run.** The data model supports many runs; the UI shows one at a time.
4. **The virtual company is fictional.** "Acme Payments" — 4 teams, 6 repos, 3 environments. No real code is executed anywhere; the sandbox is a virtual filesystem.
5. **Live Mode ships as a documented, tested ingest API with a working Python reference client.** Wiring a real Claude Code session into it is a stretch goal, not a v1 acceptance criterion.
6. **Cost figures are computed from real per-token price tables** for the models used, applied to real or simulated token counts. They are labelled "simulated spend" in the UI; nothing is billed.
7. **AWS is a deployment target, not a dependency.** Every acceptance criterion below must be satisfiable with `AGENTSHIELD_ENV=local`.

---

## App Overview

| Field | Value |
|---|---|
| **Name** | AgentShield |
| **Tagline** | Governance for the agents that write your code. |
| **Category** | AI governance / observability control plane |
| **Platform** | Web (desktop ops console) |
| **Modes** | Simulation (digital twin) · Live (real agents) |

**Elevator pitch**

Enterprises are handing coding agents real repositories, real credentials and real deployment pipelines, with almost none of the controls they spent twenty years building for human developers. AgentShield is a control plane that intercepts an agent twice — once before the model call and once before every tool call — and decides to allow, redact, hold for approval, or block. Because governance without evidence is theatre, AgentShield ships with a digital twin: a 20-person virtual company whose agents generate the exact telemetry a real fleet would, so you can test a policy before enforcing it on people, and prove the anomaly detector actually catches the insider before you trust it with one.

**Problem statement**

A platform team rolling out coding agents to 200 engineers today can answer none of these questions: which agent read which secret file last Tuesday; how much of last month's $40k model spend was an intern letting an agent retry a failing test 60 times; whether the new "interns can't use frontier models on trivial tasks" rule would block legitimate work; and whether the 2am burst of unusual repository access was a deadline or a compromised token. The data exists in six places — IDE logs, gateway logs, git history, cloud audit trails, billing exports — and is correlated by nobody. Meanwhile the only enforcement point most teams have is a per-user API key, which is an on/off switch, not a policy.

---

## User Personas

### Persona 1 — Aditi Rao, Platform Security Lead
- **Role:** Runs the developer platform and owns the AI-tooling rollout at a 400-engineer fintech.
- **Context:** Was told to "enable agents everywhere by Q3" and "make sure nothing leaks." Both, immediately.
- **Primary goal:** A single enforcement point that blocks the agent-specific failure modes — secret exfiltration through a prompt, unsanctioned production actions, silent budget burn — without her becoming the bottleneck for every deployment.
- **Pain points:** She cannot pilot a policy without risking real engineers' work. Her SIEM has no concept of "tool call." Her only evidence that a control works is that nothing has exploded yet.
- **Quote:** "I can tell you every SSH session into prod last quarter. I can't tell you a single file an agent opened."

### Persona 2 — Ben Mathew, Engineering Manager, Payments
- **Role:** Manages 8 engineers, 2 of them interns, all using coding agents daily.
- **Context:** Approvals land in his lap. He approves or denies them between meetings, from whatever context he has.
- **Primary goal:** Approve the safe ones in five seconds and catch the dangerous one, without reading a diff every time.
- **Pain points:** Requests arrive with no context — who, what repo, which environment, how risky, how much has this session already cost. He either rubber-stamps everything or becomes a blocker.
- **Quote:** "Just tell me what it's about to touch and whether this person normally does this."

### Persona 3 — Vikram Nair, CTO
- **Role:** Signs the model bill and owns the board's "are we exposed?" question.
- **Context:** Opens a dashboard once a week for ninety seconds.
- **Primary goal:** Spend, waste, risk concentration, and whether controls are actually firing — in one screen, with the ability to ask "why is Payments high?" and get a real answer.
- **Pain points:** Every AI dashboard he's shown is a token counter. None of them connect spend to risk or to prevented incidents.
- **Quote:** "Don't show me tokens. Show me what it cost and what it stopped."

### Persona 4 — Rahul Sharma, Engineering Intern (subject, not operator)
- **Role:** Six weeks in, ships small fixes with heavy agent assistance.
- **Context:** He does not use AgentShield. AgentShield governs him. He experiences it as: things work, or a message says why they didn't, or his manager gets pinged.
- **Primary goal:** Not to be blocked for no reason, and to understand the block when it happens.
- **Pain points:** Opaque tooling that fails silently. Being the person who caused the incident.

---

## Core Features (MVP)

### F1 — Gate 1: Request Governance

**Description.** Before any prompt reaches a model, AgentShield evaluates the request against identity, role, task classification, sensitive-data scan, estimated tokens, estimated cost, remaining budget and the requester's current behavioural risk. It emits one of four decisions: `allow`, `redact` (strip detected secrets, continue), `review` (hold for human approval), `block`.

**Acceptance criteria**
- [ ] Decision returns in < 50 ms p95 for local policy evaluation (excluding model call)
- [ ] A prompt containing an AWS key pattern, a private key header, a JWT or a `password=` assignment is redacted; the raw value is absent from every persisted event and from the model payload
- [ ] Redaction is reversible only via the blob store with an explicit audit event; the console shows `sk-••••••••3f2a`
- [ ] Estimated cost is computed before the call from a token estimate and the routed model's price table
- [ ] A request that would exceed the employee's daily budget returns `block` with `reason_code=budget_exceeded`
- [ ] Every decision persists the full list of `matched_policies` with their ids and versions
- [ ] Decisions are explainable: `GET /tasks/{id}` returns the ordered evaluation trace

### F2 — Gate 2: Action Governance

**Description.** Every tool call the agent attempts — read file, edit file, run tests, git push, call API, deploy, read secret, external fetch — is intercepted before execution and evaluated against tool permissions, repository scope, target environment, resource sensitivity and behavioural risk. Emits `allow`, `review` or `block`.

**Acceptance criteria**
- [ ] All 8 tools are individually governable by policy
- [ ] `read_file` on a path matching a secret pattern (`.env*`, `*.pem`, `secrets/*`, `credentials*`) is blocked for every role except `devops`, and blocked for `devops` outside their declared scope
- [ ] `deploy(environment=production)` yields `review` for engineer/intern, `allow` for devops, per seeded policy
- [ ] A blocked action returns a structured reason to the agent, and the agent's loop continues (it does not crash) and records the refusal
- [ ] Repository scope is enforced: an employee touching a repo outside `allowed_repositories` yields at minimum `review`
- [ ] Every action records `args_digest` (SHA-256 of normalised args) so identical repeated attempts are countable

### F3 — Approval Engine

**Description.** `review` decisions create an approval request routed to an approver determined by policy (team manager, senior manager, or security). Approvers see a decision card with full context. Outcomes: approve once, approve for this session, deny, or expire.

**Acceptance criteria**
- [ ] Approval card shows: requester, role, team, the exact action, target resource, environment, policy-provided reason, current risk score, session cost to date, and the requester's 7-day rate for this action type
- [ ] Approve → the held action executes and the task resumes within 500 ms
- [ ] Deny → the task terminates with `status=denied`, agent receives the refusal, event emitted
- [ ] Unanswered approvals expire after the policy TTL (default 300 sim-seconds) → `expired`, task `denied_timeout`
- [ ] `approve_session` grants the same tool+resource+environment tuple for the remainder of that task only
- [ ] Every approval decision is immutable and attributed

### F4 — The Digital Twin (20-employee simulation)

**Description.** A seeded, reproducible virtual company: 20 employees across 6 behavioural archetypes, on 4 teams, working 6 repos across 3 environments. Each has a persona defining permissions, normal hours, normal task mix, budget, mistake probability and risk tendency. One employee carries a hidden `adversarial` scenario profile that escalates over simulated days. The simulation drives the entire governance pipeline exactly as a real fleet would.

**Acceptance criteria**
- [ ] `POST /sim/runs` with a fixed seed produces byte-identical event streams across runs when `LLM_PROVIDER=mock`
- [ ] 20 employees instantiate from exactly 6 archetype templates plus one adversarial overlay
- [ ] The adversarial actor's label is stored on a separate key never read by `risk/`; a static test asserts no import path exists
- [ ] Adversarial escalation follows the 5-stage ladder: unusual repo access → secret-file attempts → external connections → token spikes → restricted operations
- [ ] At most 4 employees hold an active agent session concurrently; the rest queue or idle
- [ ] Speed control supports 1×, 10×, 100× and pause, changeable mid-run without losing state
- [ ] 7 simulated days complete in < 20 s at 100× with mock LLM
- [ ] Marquee tasks (flagged in the scenario or sampled at `llm_invocation_rate`) invoke a real model and produce genuine tool calls

### F5 — The 2D Office View

**Description.** An isometric pixel-art floorplan — CEO office, managers' room, development floor, DevOps, meeting room — with 20 avatars at desks. Status is carried by badges and halos (working / waiting approval / blocked / idle / meeting). Clicking an avatar opens a live employee drawer. A system log streams alongside. The view is a pure renderer over the telemetry stream.

**Acceptance criteria**
- [ ] 20 avatars render at ≥ 50 fps at 1× and 10× on integrated graphics
- [ ] Status badge changes within 500 ms of the corresponding event arriving over WebSocket
- [ ] Clicking an avatar opens the employee drawer (F6) without pausing the simulation
- [ ] At 100× the office switches to fast-forward mode: avatars freeze, a progress bar and a running counter replace per-event animation, and the office resyncs from a snapshot on exit
- [ ] Reloading mid-run rehydrates every avatar's position and status from `/sim/runs/{id}/state`
- [ ] Movement is cosmetic only — no simulation state depends on avatar position
- [ ] The renderer degrades to a grid-of-cards fallback if WebGL is unavailable

### F6 — Employee Drawer

**Description.** Per-employee panel: identity, role, team, agent brand, today's request/token/cost counters, allow/block/review split, risk score with its top contributing factors, current task and current status with the governing reason.

**Acceptance criteria**
- [ ] Opens in < 200 ms from cached store data, then refreshes from `/employees/{id}`
- [ ] Risk meter shows the composite 0–100 score and names its top 3 contributing features in plain language
- [ ] Shows last 10 governed decisions with timestamps and outcomes
- [ ] Shows nothing about `scenario_profile` — the operator sees only what the system inferred
- [ ] Deep-links: `/office?employee=emp_017` opens the drawer directly

### F7 — Live Feed

**Description.** The full governed event stream — every request, decision, tool call, approval and completion — as a filterable, pausable, virtualised table with an expandable trace per row.

**Acceptance criteria**
- [ ] Sustains 200 events/sec without dropped frames (virtualised list, capped in-memory buffer of 2 000)
- [ ] Filters: employee, team, decision, gate, tool, environment, risk ≥ N, free-text
- [ ] Pause freezes the view and buffers; resume flushes with a "N new events" indicator
- [ ] Expanding a row shows the full decision trace: matched policies, feature values, redactions applied
- [ ] Every row links to its task, employee and (if any) approval

### F8 — Control Center

**Description.** Policies, costs, employees, risk and incidents — the operator surface that proves this is a control plane and not a game. Includes the policy editor (JSON DSL with validation and dry-run) and the incident list produced by the risk engine.

**Acceptance criteria**
- [ ] Policy list shows id, gate, effect, priority, enabled state, version, and 24 h match count
- [ ] Creating or editing a policy validates the DSL and rejects unknown fields with the offending JSON path
- [ ] Toggling a policy takes effect on the next evaluation with no restart
- [ ] Cost view breaks spend down by team, employee and model, with a "potential waste" figure defined as spend on blocked, denied, expired and retry-loop sessions
- [ ] Incident list shows detector, score, window, evidence trail, and status

### F9 — Risk & Anomaly Engine

**Description.** Rolling per-employee behavioural baselines plus an unsupervised IsolationForest over a 12-feature session vector, blended with a static role×action sensitivity matrix into a 0–100 composite score that feeds back into both gates. Ground-truth labels are used only by the offline evaluation harness.

**Acceptance criteria**
- [ ] Trains on ≥ 2 000 simulated sessions in < 10 s
- [ ] Feature vector construction has no code path to `hidden_ground_truth` (enforced by a test that greps the import graph)
- [ ] `GET /risk/employees/{id}/explain` returns the top 3 features with z-scores and human-readable phrasing
- [ ] Risk score is an input to policy conditions (`actor.risk_score > 70`) and changes gate outcomes
- [ ] The evaluation harness prints precision, recall and time-to-detection for the hidden actor
- [ ] A cold-start employee (< 20 sessions) uses the archetype baseline, not a global one, and is flagged `low_confidence`

### F10 — Policy Lab (what-if simulator)

**Description.** Author a draft policy, replay it against the last N hours of recorded telemetry, and see projected impact before enabling it: requests affected, estimated savings, legitimate work blocked, extra approvals per day.

**Acceptance criteria**
- [ ] Replay of 24 h of events (≈ 5 000 sessions) completes in < 5 s
- [ ] Output reports: requests affected (count and %), projected spend delta, would-block count split into "previously allowed and completed successfully" (false-positive proxy) versus "previously blocked anyway", and extra approvals/day
- [ ] Draft policies are stored with `is_draft=true` and never evaluated by live gates
- [ ] One-click promote from draft to enabled, creating a new policy version

### F11 — Live Mode Ingest API

**Description.** The same gates exposed over HTTP so real agents can call them: `POST /ingest/gate1` before a model call, `POST /ingest/gate2` before a tool call, `POST /ingest/events` for telemetry. A reference Python client and an MCP-wrapper example are included.

**Acceptance criteria**
- [ ] Ingest endpoints share the *identical* code path as the simulator (same `gate1.evaluate()` call) — proven by a test that runs one fixture through both entry points and asserts identical decisions
- [ ] Bearer-token auth per agent identity; unknown token → 401
- [ ] Events from Live Mode appear in the Live Feed and Control Center alongside simulated ones, tagged `source=live`
- [ ] Reference client demonstrates a full request→tool→approval round trip in < 60 lines

### F12 — Dataset Export

**Description.** Export the generated telemetry as a labelled ML dataset — features and hidden ground truth in separate files — for training and evaluation outside the app.

**Acceptance criteria**
- [ ] `make export-dataset` writes `sessions.parquet` (features), `events.parquet` (raw), `labels.parquet` (ground truth), and a `DATASET-CARD.md` describing generation parameters and seed
- [ ] Labels file is never read by any code under `agentshield/risk/`
- [ ] 100 simulated days produce ≥ 40 000 session rows

---

## Nice-to-Have (v2)

| Feature | Why deferred |
|---|---|
| Real auth (Cognito / OIDC) + RBAC enforcement | Role switcher is enough to demo four views; real auth is a day of work with no demo payoff |
| Slack/Teams approval routing | The in-app approvals queue proves the mechanism; channel plumbing is integration work |
| Per-employee LLM-driven personalities (each employee an autonomous agent) | 20 continuous LLM loops is expensive, slow, non-deterministic and undebuggable — the explicit anti-pattern called out in the brief |
| Avatar pathfinding with collision and animated meetings | Cosmetic; costs a day; risks becoming a game |
| Multi-tenant orgs | Data model already keys by run; tenancy is a partition-key change, not a redesign |
| Streaming agent output in the office as live speech bubbles | Nice, but the drawer already carries the detail |
| Graph-based lateral-movement detection across employees | Needs more data than 4 days of simulation credibility allows |
| Policy versioning with diff/rollback UI | Versions are stored; only the UI is deferred |

---

## User Stories

| # | As a… | I want to… | So that… | Priority |
|---|---|---|---|---|
| 1 | Security lead | see every model request with its identity, cost and decision | I have one audit trail instead of six | Must |
| 2 | Security lead | have secrets stripped from prompts automatically | a leaked key never reaches a model provider | Must |
| 3 | Security lead | block agents from reading `.env.production` regardless of who asked | credential exposure has a hard stop, not a policy doc | Must |
| 4 | Security lead | test a new rule against recorded telemetry before enabling it | I stop breaking engineers' work to learn what a policy does | Must |
| 5 | Manager | receive an approval request with risk and cost context | I can decide in five seconds instead of five minutes | Must |
| 6 | Manager | approve once or for the whole session | routine work doesn't ping me eight times | Should |
| 7 | Manager | see which of my team members are trending risky | I intervene before it's an incident | Should |
| 8 | CTO | see spend, waste and blocked actions on one screen | I can answer the board without a data pull | Must |
| 9 | CTO | ask why a team is flagged high risk and get named evidence | the number means something | Should |
| 10 | Platform engineer | run the whole system locally with no cloud account | I can develop on a plane and demo without wifi | Must |
| 11 | Platform engineer | move to AWS by changing one env var | the migration is an afternoon, not a rewrite | Must |
| 12 | ML engineer | generate a large labelled telemetry dataset | I can train and evaluate a detector honestly | Must |
| 13 | ML engineer | be certain the detector never saw the labels | my precision/recall number isn't a lie | Must |
| 14 | Demo audience | watch governance happen visually in an office | the abstraction becomes concrete in ten seconds | Must |
| 15 | Demo audience | click any character and see their real governed activity | the office is obviously data, not animation | Should |
| 16 | Operator | fast-forward a simulated week and read the summary | I can evaluate a policy's weekly effect immediately | Should |
| 17 | Agent developer | call the same gates from my own agent over HTTP | governance isn't limited to the simulation | Should |
| 18 | Engineer being governed | get a clear reason when I'm blocked | I know whether to fix my request or ask for access | Should |
| 19 | Operator | pause the live feed while reading | fast streams stay legible | Could |
| 20 | Operator | deep-link to an employee, task or incident | I can paste a link into an investigation | Could |

---

## Non-Goals (Explicitly Out of Scope for v1)

- **Executing real code.** The sandbox is a virtual filesystem with simulated git, tests and deploys. Real execution adds container security scope with zero demo value.
- **Being an LLM proxy for production traffic.** Gate 1 returns a decision and routes; it is not a hardened, high-availability gateway. Latency and failover are v2 concerns.
- **Static analysis of agent-produced code.** AgentShield governs *actions and data flow*, not code quality. Scanning diffs is a different product.
- **Supervised insider-threat classification.** The detector is unsupervised by design. Labels exist solely for evaluation, per the principle in the brief: known-malicious labels are for evaluation, never for training.
- **Using the CERT insider-threat dataset.** The digital twin generates domain-correct data; CERT is human-login telemetry forced into an agent-governance shape.
- **Mobile.** An ops console at 375px is a different product.
- **Real billing or quota enforcement against a provider.** Budgets are enforced inside AgentShield, not at the provider.
- **20 independently LLM-driven employees.** Explicitly rejected: cost, latency, determinism and debuggability all fail. Behaviour comes from state machines; the model is invoked where it matters.

---

## Success Metrics

| Metric | Target | When | Measured by |
|---|---|---|---|
| Hidden-actor detection recall | ≥ 0.80 | By end of Phase 7 | `make evaluate` on a 30-sim-day run |
| False-positive rate (legitimate sessions flagged high-risk) | ≤ 0.05 | By end of Phase 7 | Same harness |
| Time-to-detection for the adversarial ladder | ≤ 2 simulated days from stage 2 | By end of Phase 7 | Incident `opened_at` minus first adversarial event |
| Gate decision latency (policy eval only) | p95 < 50 ms | Phase 2 | `pytest --benchmark` |
| 7-sim-day fast-forward | < 20 s | Phase 4 | `time make advance DAYS=7` |
| Office frame rate, 20 avatars, 10× | ≥ 50 fps | Phase 8 | Chrome perf panel |
| Reproducibility | identical SHA-256 of event stream across 2 runs, same seed | Phase 4 | `make repro-check` |
| Local→AWS switch | ≤ 30 min, zero domain-code diff | Phase 9 | `git diff --stat` on the migration commit touching only `adapters/aws`, `container.py`, `infra/` |
| Cold-start setup on a clean machine | ≤ 10 min to first simulated event | Phase 9 | README quickstart timed |
| Demo run | 3 min, unattended, zero errors | Phase 9 | `make demo` |
