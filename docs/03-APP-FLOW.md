# AgentShield — App Flow & Screen Specifications

> Styling tokens and class strings: `04-UI-UX-BRIEF.md`. API shapes: `05-BACKEND-SCHEMA.md §6`. The office canvas itself: `07-OFFICE-SIMULATION.md`.

---

## 1. Route Table

| Route | File | Layout | Purpose |
|---|---|---|---|
| `/` | — | — | redirect → `/office` |
| `/office` | `routes/office.tsx` | AppShell (full-bleed) | The 2D digital twin |
| `/office?employee=emp_017` | same | same | Office with the employee drawer open |
| `/live` | `routes/live.tsx` | AppShell (padded) | Governed event stream |
| `/live/:taskId` | same | same | Live feed with the task trace drawer open |
| `/approvals` | `routes/approvals.tsx` | AppShell (padded) | Manager approval queue |
| `/control` | `routes/control/index.tsx` | AppShell + ControlNav | Executive overview |
| `/control/policies` | `routes/control/policies.tsx` | AppShell + ControlNav | Policy list + editor |
| `/control/policy-lab` | `routes/control/policy-lab.tsx` | AppShell + ControlNav | What-if simulator |
| `/control/employees` | `routes/control/employees.tsx` | AppShell + ControlNav | Employee table |
| `/control/costs` | `routes/control/costs.tsx` | AppShell + ControlNav | Spend and waste |
| `/control/risk` | `routes/control/risk.tsx` | AppShell + ControlNav | Risk leaderboard + explain |
| `/control/incidents` | `routes/control/incidents.tsx` | AppShell + ControlNav | Incident list + detail |

No auth routes in v1. The role selector in the header is a client-side view filter only (`uiStore.viewAs`).

---

## 2. Navigation

```
                      ┌──────────────────────────────────────────┐
                      │ AppShell header (always present)         │
                      │  shield · OFFICE  LIVE  APPROVALS  CONTROL│
                      │  ………  run pill · sim clock · speed · role │
                      └──────────────────────────────────────────┘
                                        │
   ┌──────────────┬─────────────────────┼──────────────────┬───────────────────┐
   ▼              ▼                     ▼                  ▼                   │
/office         /live               /approvals          /control ──── ControlNav
   │              │                     │                  │        ├ /policies
   │ click        │ click row           │ decide           │        ├ /policy-lab
   │ avatar       ▼                     │                  │        ├ /employees
   ▼         task trace drawer          │                  │        ├ /costs
employee drawer   │                     │                  │        ├ /risk
   │              │ "view employee"     │ "view task"      │        └ /incidents
   ├──────────────┴─────────────────────┴──────────────────┘
   ▼
"View full activity" → /control/employees?focus=emp_017
"Explain risk"       → /control/risk?employee=emp_017
```

Cross-links that must exist (every one is a demo beat):

- Office avatar → employee drawer → **Explain risk** → `/control/risk?employee=…`
- Live feed row → task trace → **Employee** → `/office?employee=…`
- Approvals card → **View task** → `/live/:taskId`
- Incident → **Evidence event** → `/live?seq=…`
- Exec overview "Why is Payments high?" → `/control/risk?team=payments`

---

## 3. Shared Layout

### AppShell — `components/layout/AppShell.tsx`

Header, 56px, fixed. Left to right:

1. Shield mark (24px) — links to `/office`
2. Four primary nav items: `OFFICE` `LIVE FEED` `APPROVALS` `CONTROL CENTER`, each with its icon; active item carries the underline treatment from the UI brief
3. Spacer
4. **Run pill** — `run_7f3a · day 14` — click opens the run switcher popover
5. **Sim clock** — `Tue 09:21` in the pixel display face, plus a small `×10` badge when not at 1×
6. **Speed control** — four segmented buttons: `▶ REAL TIME` `▶▶ 10×` `▶▶▶ 100×` `⏸ PAUSE`
7. **Connection dot** — green connected, amber reconnecting, red offline
8. **Approvals badge** — bell with a count; pulses once when the count increases
9. **Role selector** — `Security · Manager · CEO · Engineer`

Body fills the remaining height. Two body modes:
- `full-bleed` (office): no padding, no scroll, canvas owns the space
- `padded`: `max-w-[1600px] mx-auto px-6 py-5`, page scrolls

### Speed control behaviour

| Action | Effect |
|---|---|
| Click `REAL TIME` / `10×` | `POST /sim/runs/{id}/control {action:"set_speed", speed}` — office keeps animating |
| Click `100×` | Opens the **Fast-forward dialog** (§7.1) rather than switching immediately |
| Click `PAUSE` | `{action:"pause"}`; office dims to 60% opacity and shows a `PAUSED` chip; the Live Feed keeps its buffer |
| Click a paused speed button | `{action:"resume"}` at that speed |
| Server auto-downshifts (tick overrun) | toast: *"Dropped to 1× — ticks were overrunning."* Speed control reflects the new value. |

### Global toasts

| Trigger | Style | Text | Dismiss |
|---|---|---|---|
| Approval decided | success | `Approved — Rahul's deployment is continuing.` | 3 s |
| Approval denied | neutral | `Denied. The task was terminated.` | 3 s |
| Policy saved | success | `Policy saved as v{n}. Active on the next evaluation.` | 3 s |
| Policy invalid | error | `{message} at {field}` | manual |
| Incident opened | warning | `Incident opened: {employee} — {summary}` + **View** | 6 s |
| WS reconnected after a gap | neutral | `Reconnected. Resynced {n} events.` | 3 s |
| Telemetry degraded | error | `Events are being buffered locally — storage is not responding.` | manual |
| Speed downshift | warning | `Dropped to 1× — ticks were overrunning.` | 5 s |

Position: bottom-right, stacked, max 3 visible.

### Global error and connection states

| Condition | Presentation |
|---|---|
| API unreachable on load | Full-page state: *"Can't reach the AgentShield API."* + the configured base URL + **Retry** |
| WS disconnected | Header dot amber, thin amber line under the header, `Reconnecting…` tooltip. Data stays on screen; nothing clears. |
| No run exists | Full-page state: *"No simulation yet."* + **Create a run** (opens §7.2) |
| Run reset while viewing | Toast + automatic navigation to `/office`, stores cleared |
| 404 route | *"That page doesn't exist."* + **Back to the office** |

---

## 4. Screen: `/office` — The Digital Twin

**File:** `routes/office.tsx` · **Layout:** AppShell full-bleed

### Composition

```
┌──────────────────────────────────────────────────────────────┬──────────────┐
│                                                              │  SYSTEM LOG  │
│                                                              │              │
│              <PhaserGame />   (isometric office canvas)      │  09:15 Intern│
│                                                              │  Rahul req…  │
│                                                              │  09:20 Codex │
│                                                              │  184K tokens │
│                                                              │  09:21 Task  │
│  ┌────────────────────────────┐                              │  BLOCKED by  │
│  │ employee drawer (overlay)  │                              │  Gate 2      │
│  └────────────────────────────┘                              │  09:25 Ben   │
│                                                              │  review req  │
│  [− zoom +]  [⤢ fit]           legend: ● working ● waiting   │              │
│                                         ● blocked ● idle     │  340px       │
└──────────────────────────────────────────────────────────────┴──────────────┘
```

### UI elements

- **Canvas** — `<PhaserGame />`, fills the left region. Full spec in `07-OFFICE-SIMULATION.md`.
- **System log** — fixed 340px right rail. Monospace, newest at top, auto-scrolls unless the user has scrolled up (then a `↓ N new` pill appears). Each line: `[HH:MM] <text>` with the decision word coloured by its signal colour. Capped at 200 lines. Lines are rendered from the same `telemetryStore` events, formatted by `lib/format.ts::describeEvent()`.
- **Zoom controls** — bottom-left, `−` / `+` / `fit`. Zoom range 0.5–2.0.
- **Legend** — bottom-centre, four status dots with labels.
- **Employee drawer** — right-side overlay panel, 420px, above the canvas (§5).
- **Fast-forward overlay** — replaces the canvas at 100× (§7.1).

### Data

| What | Source | When |
|---|---|---|
| Office snapshot | `GET /sim/runs/{id}/state` | on mount, on reconnect gap > 500, on exiting 100× |
| Live events | WebSocket → `telemetryStore` | continuously |
| Employee roster | `GET /employees?run_id` (TanStack, `staleTime: 60s`) | on mount |

### Interactions

| Action | Result |
|---|---|
| Click an avatar | Opens the employee drawer; sets `?employee=<id>`; camera pans to centre that desk over 300 ms |
| Click empty floor | Closes the drawer; clears the query param |
| Drag canvas | Pans the camera (clamped to map bounds) |
| Scroll wheel | Zooms toward the cursor |
| Hover an avatar | Tooltip: name, role, current status, risk score |
| Click a system-log line | Opens the related task trace at `/live/:taskId` |
| Press `Esc` | Closes the drawer |
| Press `Space` | Toggles pause |

### States

- **Loading:** canvas area shows the office floor plan as a static dimmed image with a centred `Loading the floor…` label; the system log shows three skeleton lines.
- **Empty (run exists, no activity yet):** avatars render idle; the system log shows *"Waiting for the first request. Press ▶ to start."*
- **Error (snapshot fails):** canvas replaced by the card-grid fallback (`07-OFFICE-SIMULATION.md §11`) plus a banner: *"Couldn't load the floor. Showing a simple view."* + **Retry**.
- **No WebGL:** card-grid fallback, no banner (it is a legitimate mode, not an error).
- **Paused:** canvas at 60% opacity, centred `PAUSED` chip, log frozen.

---

## 5. Component: Employee Drawer

**File:** `components/employee/EmployeeDrawer.tsx`
**Trigger:** clicking an avatar; `/office?employee=`; the "view employee" link anywhere.

```
┌────────────────────────────────────────────┐
│  ⬛ sprite     RAHUL SHARMA              ✕ │
│               Engineering Intern · Payments│
│               Agent: Codex                 │
├────────────────────────────────────────────┤
│  TODAY                                     │
│  Requests   23     Tokens    184K          │
│  Cost    $3.84     Sessions      4         │
│                                            │
│  Allowed 18   Blocked 2   Review 3         │
├────────────────────────────────────────────┤
│  RISK                                      │
│  ██████░░░░  61  /100      normal confidence│
│  · 3.1× normal token usage today           │
│  · 2 blocked secret-file attempts          │
│  · Touched 1 repo outside his usual two    │
│                            [ Explain risk ]│
├────────────────────────────────────────────┤
│  CURRENT TASK                              │
│  "Fix payment API error"                   │
│  payments-api · production                 │
│                                            │
│  ⚠ WAITING FOR APPROVAL                    │
│  Agent attempted production deployment.    │
│                          [ View request → ]│
├────────────────────────────────────────────┤
│  RECENT DECISIONS                          │
│  09:21  read_file .env.production   BLOCKED│
│  09:20  run_tests payments-api      ALLOW  │
│  09:18  edit_file handlers/pay.py   ALLOW  │
│  …                                         │
├────────────────────────────────────────────┤
│  [ View full activity ]                    │
└────────────────────────────────────────────┘
```

**Data:** `GET /employees/{id}?run_id` on open (TanStack, `staleTime: 5s`); live counters patched from `telemetryStore` events for that employee so numbers move while the drawer is open.

**Interactions**
- `Explain risk` → `/control/risk?employee=<id>`
- `View request →` → `/approvals?focus=<approval_id>` when awaiting approval, else `/live/:taskId`
- Recent decision row → `/live/:taskId` with that action expanded
- `View full activity` → `/control/employees?focus=<id>`
- `✕` or `Esc` → close, clear query param

**States**
- Loading: header (sprite + name) renders from the store immediately; the three body sections show skeletons.
- Empty (no activity today): counters show `0`; current-task block reads *"Nothing in progress."*
- Low-confidence risk: the meter is rendered with a hatched fill and the label reads `low confidence — building baseline (14/20 sessions)`.
- Error: *"Couldn't load this employee."* + **Retry**; the header stays visible.

**Never shows** `scenario_profile`. The operator sees only what the system inferred. This is not a UI preference — the API does not return it.

---

## 6. Screen: `/live` — Live Feed

**File:** `routes/live.tsx` · **Layout:** AppShell padded

### Composition

```
┌────────────────────────────────────────────────────────────────────────┐
│ Filters:  [employee ▾] [team ▾] [gate ▾] [decision ▾] [tool ▾]        │
│           [risk ≥ __] [search…]            [⏸ Pause]  1,284 events     │
├──────┬──────────┬─────────┬──────────┬────────────┬────────┬──────────┤
│ TIME │ WHO      │ GATE    │ WHAT     │ RESOURCE   │ DECISION│ COST     │
├──────┼──────────┼─────────┼──────────┼────────────┼────────┼──────────┤
│09:21 │ Rahul S. │ Gate 2  │read_file │payments-api│ BLOCK  │  —       │
│      │ intern   │         │          │.env.prod   │        │          │
│09:20 │ Rahul S. │ —       │model     │haiku       │  —     │ $0.014   │
│09:18 │ Priya S. │ Gate 1  │request   │payments-api│ ALLOW  │ ~$0.09   │
│  …   │          │         │          │            │        │          │
└──────┴──────────┴─────────┴──────────┴────────────┴────────┴──────────┘
```

### Behaviour

- Virtualised via `@tanstack/react-virtual`; the in-memory buffer holds 2 000 events, oldest evicted.
- New events prepend with a 120 ms highlight flash on the row background. At > 40 events/sec the flash is suppressed (measured by a rolling counter) so the table stays readable.
- **Pause** freezes rendering and buffers; the button becomes `▶ Resume (N new)`.
- Scrolling away from the top auto-pauses and shows a `↑ Jump to latest` pill.
- Row click expands an inline trace panel (§6.1). Only one row is expanded at a time.

### Filters

| Filter | Type | Options |
|---|---|---|
| employee | multi-select | roster, with sprite thumbnails |
| team | multi-select | payments, platform, frontend, data, exec |
| gate | segmented | all / gate 1 / gate 2 / neither |
| decision | multi-select | allow, redact, review, block |
| tool | multi-select | the 8 tools |
| risk ≥ | number 0–100 | filters on `risk_at_request` |
| search | text, debounced 250 ms | matches resource, title, policy id, task id |

Filters apply client-side to the buffer **and** are pushed to `GET /events` as query params when the user scrolls past the buffer.

### 6.1 Inline trace panel

```
┌──────────────────────────────────────────────────────────────────────┐
│ task_9c21 · Rahul Sharma · "Fix payment API error"                    │
│                                                                       │
│ TIMELINE                                                              │
│  ● 09:15  task.requested        bug_fix · payments-api · production   │
│  ● 09:15  gate1.decision        ALLOW   · est $0.09 · haiku           │
│  ● 09:16  model.invoked         1,204 in / 380 out · $0.011           │
│  ● 09:17  gate2.decision        ALLOW   read_file src/handlers.py     │
│  ● 09:18  gate2.decision        ALLOW   run_tests payments-api        │
│  ● 09:21  gate2.decision        BLOCK   read_file .env.production     │
│           matched: pol_block_secret_read (v1, priority 200)           │
│  ● 09:22  gate2.decision        REVIEW  deploy payments-api / prod    │
│           matched: pol_prod_deploy_requires_manager → approval pending │
│                                                                       │
│ DECISION DETAIL (selected event)                                      │
│  Context evaluated:  role=engineering_intern  repo_in_scope=true      │
│                      is_secret_path=true      risk_score=61           │
│  Redactions: none                                                     │
│                                                                       │
│  [ View employee ]  [ View approval ]  [ Copy task id ]               │
└──────────────────────────────────────────────────────────────────────┘
```

**Data:** `GET /tasks/{task_id}` (one docstore query, A9).

### States

- **Loading:** eight skeleton rows.
- **Empty (filters match nothing):** *"No events match these filters."* + **Clear filters**.
- **Empty (run not started):** *"No events yet. Start the simulation to see governed activity."* + **Start** (calls control).
- **Error:** *"Couldn't load events."* + **Retry**; any buffered events stay visible above the error strip.

---

## 7. Dialogs on the Office / Shell

### 7.1 Fast-forward dialog (100×)

Opened by clicking `100×`.

```
┌────────────────────────────────────────────┐
│  Fast-forward the simulation             ✕ │
│                                            │
│  How far?                                  │
│  ( ) 1 day    (•) 1 week    ( ) Custom __  │
│                                            │
│  Avatars pause while this runs. The office │
│  resyncs when it finishes.                 │
│                                            │
│              [ Cancel ]  [ Run ]           │
└────────────────────────────────────────────┘
```

On **Run**: `POST /sim/runs/{id}/advance`. The canvas is replaced by the progress overlay:

```
        SIMULATING 7 DAYS
        ████████████░░░░░░  day 5 of 7
        14,204 events generated
```

Progress comes from WS `progress` frames. On completion the overlay becomes the summary card:

```
        SIMULATION COMPLETE
        ────────────────────────────
        2,413   agent requests
        2.1M    tokens
        47      blocked actions
        18      approvals
        $92     avoidable spend identified
        3       behavioural anomalies
        ────────────────────────────
        [ View incidents ]  [ Back to the office ]
```

`Back to the office` refetches `/sim/runs/{id}/state` and resumes the stream. `View incidents` → `/control/incidents`.

**Error:** if `advance` fails, the overlay shows *"The fast-forward stopped at day {n}."* + **Back to the office**; the run remains usable at whatever sim time it reached.

### 7.2 Create-run dialog

Fields: `seed` (number, default from server, helper *"Same seed, same simulation"*), `employee_count` (5–50, default 20), `scenario` (select: `demo`, `baseline`, `stress`), `seed history` (checkbox, default on, helper *"Pre-run 14 days so risk baselines exist"*).

Submit → `POST /sim/runs`, then `POST .../advance {sim_days:14}` if history is checked, then navigate to `/office`.

---

## 8. Screen: `/approvals` — Approval Queue

**File:** `routes/approvals.tsx` · **Layout:** AppShell padded

```
┌───────────────────────────────────────────────────────────────────────┐
│  Pending (3)          Decided today (12)                              │
├───────────────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────────────────────┐ │
│ │ ⚠  Rahul Sharma · Engineering Intern · Payments      expires 4:12 │ │
│ │                                                                   │ │
│ │ The agent wants to:   deploy  payments-api                        │ │
│ │ Environment:          PRODUCTION                                  │ │
│ │ Why you're seeing it: Production deployment requires manager      │ │
│ │                       approval.  (pol_prod_deploy_requires_manager)│ │
│ │                                                                   │ │
│ │ Risk 71/100   Session cost $0.38   Rahul has deployed to prod     │ │
│ │                                    0 times in the last 7 days.    │ │
│ │                                                                   │ │
│ │ [ View task ]              [ Deny ]  [ Approve once ] [ Approve   │ │
│ │                                                        session ]  │ │
│ └───────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

**Data:** `GET /approvals?run_id&status=pending` polled every 5 s via TanStack, invalidated immediately by `approval.requested` / `approval.decided` events on the WS.

**Interactions**

| Action | Result |
|---|---|
| `Approve once` | `POST /approvals/{id}/decide {decision:"approve_once"}`; card animates out; toast; the office badge turns green within 500 ms |
| `Approve session` | same with `approve_session`; card shows a brief `session` chip before leaving |
| `Deny` | opens a small inline note field (optional, 500 chars) then submits `deny` |
| `View task` | `/live/:taskId` |
| Countdown reaches 0 | Card greys out, stamps `EXPIRED`, removes itself after 2 s |
| Keyboard `a` / `d` | Approve once / Deny the focused card |

**States**

- Loading: three skeleton cards.
- Empty: centred — shield icon, *"Nothing waiting on you."*, sub: *"Approval requests appear here the moment a policy holds an action."*
- Error: *"Couldn't load approvals."* + **Retry**.
- Optimistic failure: if `decide` returns `409`, the card is restored with a warning strip: *"Someone already decided this."*

**Decided-today tab:** compact table — time, requester, action, decision, approver, note. Read-only.

---

## 9. Screen: `/control` — Executive Overview

**File:** `routes/control/index.tsx` · **Layout:** AppShell padded + ControlNav

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ControlNav:  Overview | Policies | Policy Lab | Employees | Costs |      │
│              Risk | Incidents                                           │
├─────────────────────────────────────────────────────────────────────────┤
│  20            387           $142          $38           21        8    │
│  AI-enabled    requests      spend         waste         blocked   appro│
│  employees     today         today         prevented     actions   vals │
├──────────────────────────────────┬──────────────────────────────────────┤
│  AI SPEND BY TEAM                │  RISK BY TEAM                        │
│  Payments   ████████████  $74    │  Payments   HIGH    ▸                │
│  Platform   ██████        $31    │  Platform   MEDIUM  ▸                │
│  Frontend   ████          $22    │  Frontend   LOW     ▸                │
│  Data       ███           $15    │  Data       LOW     ▸                │
├──────────────────────────────────┴──────────────────────────────────────┤
│  WHY IS PAYMENTS HIGH?                                                  │
│  · 4 production access attempts                                         │
│  · unusual late-night activity (3 sessions after 01:00)                 │
│  · 5.8× token usage spike on one account                                │
│  · 1 secret-file access attempt, blocked                                │
│                                            [ Investigate Payments → ]   │
├─────────────────────────────────────────────────────────────────────────┤
│  7-DAY TREND    spend ▁▂▃▅▆▇█   blocked ▁▁▂▁▄▂▃   approvals ▂▃▂▄▃▅▄     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Data:** `GET /metrics/summary?run_id&scope=exec` (`refetchInterval: 10s`).

**Interactions**
- Any stat card → its detail route (`spend` → `/control/costs`, `blocked` → `/live?decision=block`, `approvals` → `/approvals`, `waste` → `/control/costs?view=waste`)
- Team risk row `▸` → `/control/risk?team=<team>`
- `Investigate Payments →` → `/control/risk?team=payments`

**Role adaptation (`uiStore.viewAs`)**
- `ceo` — exactly the layout above.
- `security_admin` — the same six stats, but the lower half is replaced by open incidents and the top-10 risk leaderboard.
- `manager` — stats scoped to the manager's team; the "why" panel lists their own team members.
- `engineer` — stats scoped to that individual; risk panel replaced by "your recent decisions".

**States:** loading → six stat-card skeletons plus two chart skeletons. Empty (no activity) → all zeros with an inline hint *"No governed activity yet today."* Error → *"Couldn't load the overview."* + **Retry**.

---

## 10. Screen: `/control/policies`

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Policies (12 active, 1 draft)                     [ + New policy ]     │
├────┬────────────────────────────┬──────┬────────┬─────┬────────┬────────┤
│ ON │ NAME                       │ GATE │ EFFECT │ PRI │ 24H    │ VER    │
├────┼────────────────────────────┼──────┼────────┼─────┼────────┼────────┤
│ ●  │ Block secret file reads    │  2   │ BLOCK  │ 200 │  7     │ v1     │
│ ●  │ Prod deploy needs manager  │  2   │ REVIEW │ 180 │  4     │ v3     │
│ ○  │ Interns: model downgrade   │  1   │ ALLOW  │  95 │  —     │ draft  │
└────┴────────────────────────────┴──────┴────────┴─────┴────────┴────────┘
```

Clicking a row opens the **policy editor** as a right-side sheet (640px):

- **Name** — text, 3–80 chars
- **Gate** — segmented `Gate 1 (request)` / `Gate 2 (action)`; switching gates re-validates the condition against that gate's field allowlist
- **Effect** — segmented `allow` / `redact` / `review` / `block`; `redact` is disabled at Gate 2 with a tooltip
- **Priority** — number 0–999
- **Approver** — role select + scope select; shown only when effect is `review`; required
- **TTL** — number of sim-seconds, 30–86 400, shown only when effect is `review`
- **Route override** — select `trivial|standard|complex`, shown only when effect is `allow` at Gate 1
- **Message** — text 5–200, helper: *"Shown to the requester and on the approval card."*
- **Condition** — CodeMirror JSON editor with the field allowlist as autocomplete; live validation calls `POST /policies/validate` debounced 400 ms

Footer: `Test against last 24h` (→ opens Policy Lab pre-filled), `Save as draft`, `Save and enable`.

**Validation errors** render inline under the editor with the JSON path highlighted: `when.all[1].field — unknown field "actor.department". Did you mean "actor.team"?`

**States:** loading → six skeleton rows. Empty → *"No policies yet."* + **Add the starter set** (runs the seed). Error → retry.

---

## 11. Screen: `/control/policy-lab`

```
┌──────────────────────────────┬──────────────────────────────────────────┐
│  DRAFT POLICY                │  PROJECTED EFFECT                        │
│                              │                                          │
│  [ name ]                    │  Requests affected          218  (8.4%)  │
│  [ gate ][ effect ][ pri ]   │  Estimated savings       −$21.40  (21%)  │
│                              │  Would block work that                   │
│  ┌──────────────────────┐    │  previously succeeded         3  (0.1%)  │
│  │ { "all": [           │    │  Extra approvals per day       14        │
│  │    { "field": …      │    │                                          │
│  │  ] }                 │    │  AFFECTED BY ROLE                        │
│  └──────────────────────┘    │  intern ████████ 180                     │
│                              │  engineer ██ 38                          │
│  Replay window               │                                          │
│  ( ) 6h  (•) 24h  ( ) 7d     │  SAMPLE (10 of 218)                      │
│                              │  task_1a2b  Rahul  trivial  sonnet→haiku │
│  [ Run against digital twin ]│  task_3c4d  Zoya   trivial  sonnet→haiku │
│                              │                                          │
│                              │       [ Promote to active policy ]       │
└──────────────────────────────┴──────────────────────────────────────────┘
```

**Data:** `POST /policy-lab/simulate`. The right panel is empty until the first run.

**Interactions**
- `Run against digital twin` → validates first; on error, shows the inline validation state and does not call simulate
- `Promote to active policy` → `POST /policy-lab/promote`, then navigates to `/control/policies` with the new row highlighted for 2 s
- Sample row → `/live/:taskId`

**States**
- Initial: right panel shows *"Write a condition and run it. Nothing is enforced until you promote it."*
- Running: right panel shows a progress line *"Replaying 5,120 decisions…"* with a determinate bar
- Empty result (0 affected): *"This policy wouldn't have changed anything in the last 24 hours."* + a hint to widen the window
- Error: *"The replay failed."* + **Retry**

---

## 12. Screen: `/control/employees`

Dense table, sortable, one row per employee:

| Column | Notes |
|---|---|
| Employee | sprite + name + role |
| Team | |
| Agent | claude_code / codex / internal / mcp |
| Requests (today) | |
| Tokens | humanised, `184K` |
| Cost | `$3.84`, red when over budget |
| Allow / Review / Block | three small numbers |
| Risk | 0–100 with the bar treatment; hatched when low confidence |
| Status | current `TaskStatus` chip |

Row click → `EmployeeDrawer` (same component as the office). `?focus=emp_017` scrolls to and highlights the row for 2 s.

**Filters:** team, role, risk ≥, status, agent brand. **Sort:** any numeric column, default risk desc.

**States:** loading → ten skeleton rows. Empty → *"No employees in this run."* Error → retry.

---

## 13. Screen: `/control/costs`

Three stacked sections:

1. **Spend over time** — stacked area by team, 7 or 30 sim-days, toggle. `GET /metrics/spend?group_by=team&days=`
2. **Breakdown** — segmented `By team | By employee | By model`; horizontal bar list with usd, tokens and a `waste` sub-bar in the waste colour
3. **Waste detail** (`?view=waste` deep-links here) — table of sessions counted as waste, with the reason chip (`blocked` / `denied` / `timeout` / `retry loop` / `failed`), the cost, and a link to the task

A note under the waste table states the definition verbatim from `05-BACKEND-SCHEMA.md §4` so the number is never ambiguous in a demo.

**States:** loading → chart skeleton + five bar skeletons. Empty → *"No spend recorded yet."* Error → retry.

---

## 14. Screen: `/control/risk`

```
┌──────────────────────────┬──────────────────────────────────────────────┐
│ RISK LEADERBOARD         │  NIKHIL RAO · Engineer · Platform            │
│                          │  ██████████████████░░  84 / 100              │
│ ● Nikhil Rao      84  ▸  │  static 61 · behavioural 92 · ml 88          │
│ ● Rahul Sharma    61  ▸  │                                              │
│ ● Ishaan Bose     54  ▸  │  TOP FACTORS                                 │
│ ● Mark Dsouza     38  ▸  │  1. 5.8× his normal token usage    z = 3.9   │
│ ● Priya Sharma    22  ▸  │  2. 4 blocked secret-file attempts z = 3.4   │
│                          │  3. 31% of activity after 01:00    z = 2.8   │
│ [ team filter ▾ ]        │                                              │
│                          │  BASELINE vs NOW                             │
│                          │  tokens/session   4,100 ± 900    →  23,800   │
│                          │  repos touched         2.1       →       6   │
│                          │  off-hours frac       0.04       →    0.31   │
│                          │                                              │
│                          │  RECENT CONTRIBUTORS                         │
│                          │  02:13  read_file secrets/db.yaml   BLOCKED  │
│                          │  02:19  external_fetch paste.ee     BLOCKED  │
│                          │  02:41  git_push infra-terraform    REVIEW   │
│                          │                                              │
│                          │  [ Open incident ]  [ View all activity ]    │
└──────────────────────────┴──────────────────────────────────────────────┘
```

**Data:** `GET /risk/employees` (list) and `GET /risk/employees/{id}/explain` (detail).

`?employee=` or `?team=` pre-selects. Every factor is phrased in plain language by the API, not by the client — the wording lives in `risk/scoring.py` so the API, the drawer and this screen never disagree.

**States:** loading → list skeleton + detail skeleton. Empty → *"Not enough activity to score anyone yet."* + *"Risk needs 20 sessions per person; run `make seed-history` or fast-forward a week."* Error → retry.

---

## 15. Screen: `/control/incidents`

List of incidents, newest first: severity dot, employee, detector, score, opened time, status chip, one-line summary.

Expanding shows the evidence trail — each row is `sim_ts · kind · detail` and links to the event in the Live Feed. Actions: `Acknowledge`, `View employee`, `View risk explanation`.

**States:** loading → four skeleton rows. Empty → *"No incidents. That's the goal."* (with a quieter tone than an error state). Error → retry.

---

## 16. Loading, Empty and Error — the rules

Applied everywhere, no exceptions:

| State | Rule |
|---|---|
| Loading | Skeletons shaped like the real content. Never a centred spinner on a full page. Header and nav always render immediately. |
| Empty | One line saying what would be here, one line saying how to make it appear, and a button that does that thing when one exists. |
| Error | What failed, in plain words, plus **Retry**. Never a stack trace, never a raw HTTP code, never an apology. Already-loaded data stays on screen. |
| Partial failure | Render what loaded; put the error strip only on the failed section. |
| Stale while reconnecting | Keep showing data, mark the header dot amber. Do not clear the screen because a socket dropped. |
