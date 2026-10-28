---
name: agentshield-office-frontend
description: Use when working in apps/web — the 2D office canvas, stores, WebSocket stream, console routes, or anything that renders telemetry. Explains store ownership, the renderer-over-telemetry rule, and rehydration semantics.
alwaysApply: false
globs:
  - "apps/web/src/**/*.{ts,tsx}"
  - "apps/web/vite.config.ts"
---

# The office console: renderer over telemetry

The 2D office is a **renderer over the event stream**. It holds no authoritative state;
if the canvas and the API disagree, the API is right and the canvas resnapshots. The
card-grid fallback (`components/office/AvatarGrid.tsx`) must always keep working — it
reads the same store, so it stays in sync for free.

## Store ownership (never blur this)

| Store | Owns | Written by |
|---|---|---|
| `telemetryStore` | the event stream: `events` (ring cap 2000), `officeQueue` (cap 400, only the 6 office event types), `log` (cap 200), `lastSeq`, `connected`, `paused` | WebSocket only (`ingest`) |
| `simStore` | run, employees, avatars, pendingApprovals, simTs, speed, progress | REST (`loadRun`, `refreshSnapshot`) and `applyEvent` folding events into avatar FSM |
| `uiStore` | selection, drawers, pause flags | UI interactions |

REST and WS never write the same slice, so nothing reconciles them. The canvas reads
`simStore.avatars` — it never computes state from raw events itself, and never fetches.
Keep `src/game/` free of `fetch`/WebSocket/API imports.

## WebSocket semantics (`lib/ws.ts` + backend `api/ws.py`)

- Reconnect resumes from `lastSeq` (a **sequence cursor**, never a timestamp).
- Server replays gaps; a gap over 500 events sends a `snapshot` frame — the client then
  calls `refreshSnapshot(runId)`, applies the avatar state as a **hard cut (no tweens)**,
  sets `lastSeq` to the snapshot's `seq`, and clears `officeQueue`. Animating a catch-up
  would be a lie about when things happened.
- Backoff is exponential, capped at 10s (a server restart must not create a thundering
  herd). 20s client ping; server heartbeat every 15s.
- One socket for the app's lifetime, opened in `App.tsx` — navigation must not drop it.

## The living-office engine (`src/game/engine/`)

The office is not hand-animated: furniture, movement and seats are **derived from the
room art itself**. The pipeline (all stdlib-only Python, re-runnable):

1. `infra/scripts/straighten_and_grow.py` — the AI-rendered room PNGs arrive with
   residual shear/scale drift; this warps each room's slab rim (measured from the void
   bottom envelope — never occluded, no color model) EXACTLY onto the canonical 64x32
   lattice (3-point affine, W/S/E tips -> nominal rim diamond), then GROWS rooms to the
   symmetric 32x32 building by whole-tile cloning of open floor. Idempotent: reads
   `infra/rooms_v1/` (pre-surgery art), writes `office/rooms/*.png` + new CALIBRATION
   values. Never hand-edit `rooms/*.png`.
2. `infra/scripts/extract_furniture.py` — samples each tile's floor plane (occlusion)
   and mid-column (tall bulk) to produce `footprints.generated.ts`; employee anchor
   tiles are force-walkable. Extraction runs against the ARCHIVE art (`rooms_v1/`):
   the warp is lattice-locked (furniture keeps its local tile), so footprints stay
   valid across warps. The script mirrors EmployeeCatalog seats in
   `employee_catalog_data.py` — keep the two in sync.
3. `infra/scripts/make_character_atlas.py` — generates the animated character atlas
   (`characters/atlas.png`, 8 looks x 4 facings x walk/idle/type/sit, silhouette
   outline + per-look accessories) plus the frame table as a TS module
   (`atlasFrames.generated.ts`) — src/game may not fetch JSON.

`calibrate.html` (tile grid + footprints + anchors over the art) and `seats.html`
(meeting seat proposals) are the visual regression tools; `office-harness.html` runs
the real engine without the app shell. If people clip furniture or walls: re-run the
pipeline in order, then check the calibration page — never fix by nudging coordinates
in movement code.

## Avatar state semantics

- FSM from task status: `working` / `waiting` (awaiting approval) / `blocked` / `idle`.
- The anomaly overlay is **not a state**: set at `risk_score >= 70`, cleared below 60
  (hysteresis, both in `simStore.badgeFor` and backend `sim/snapshot.py`). Someone can be
  working AND flagged — that's the most interesting thing the demo shows.
- Desk positions come from the server (`seed.py` via `office_map.py`); never shuffle them
  client-side or rehydration becomes fiction.

## Canvas architecture (`game/`)

- `OfficeSimulation.tsx` owns the RAF loop, camera (drag pan, stepped wheel zoom, DPR-aware
  resize) and the DOM HUD (name plates, status pills, popover card).
- `WorldRenderer` pre-renders room backgrounds off-screen once; `PersonRenderer` draws
  pixel sprites + halos; `MotionSystem` does walk/idle interpolation; `IsoMath` is the
  2:1 projection and `depth = (tx + ty)` ordering — characters must never render behind
  their desks.
- Per-frame cost matters: the office pump drains `officeQueue` (max N events/frame), never
  walks the full 2000-event buffer.

## API client rules (`lib/api.ts`)

- All responses are `{data: ...}`; non-2xx raise `ApiError{status, code, field?}` — the
  policy editor uses `field` (the JSON path) to underline the exact condition node.
- Network failure is `ApiError(0, 'unreachable')` — show "Can't reach the AgentShield
  API", don't retry-loop.
- New endpoint? Add a typed helper in `endpoints`, use TanStack Query for reads.

## Verify

```bash
python tasks.py test-web && python tasks.py lint-web && python tasks.py build
```

Also run the office isolation test (the canvas must not import the API layer):
`npm test -- office-isolation` (in `apps/web`).
