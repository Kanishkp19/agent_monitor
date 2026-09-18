# AgentShield — The Office Simulation (2D Isometric View)

> This document specifies the visual layer only. It has no authority over simulation state. Every pixel here is a rendering of events that already happened server-side. Read `DESIGN.md §11` for the data-flow rules before building any of it.

---

## 0. The One Rule

**The office is a renderer, not a simulator.**

- It holds no truth. Closing the tab changes nothing.
- It cannot start, stop, approve, block, or schedule anything. It can only *ask* the API, and the API tells the server, and the server sends back an event, and the event changes what you see.
- Avatar position, walking, and idle animation are decorative. No governed outcome depends on where a character is standing.
- If the office and the Live Feed ever disagree, the Live Feed is right and the office resnapshots.

The budget for the entire visual layer is **one day**. When the day ends, whatever is unfinished gets cut, not extended. The fallback in §11 exists precisely so cutting is survivable.

---

## 1. The Look

The reference is a cutaway isometric office: rooms as separate floating islands on a dark background, brick walls on two sides, floor tiles inside, furniture and characters on top, black gaps where the walls would meet. This layout is chosen for engineering reasons as much as aesthetic ones — separate islands mean **no doors, no corridors, no inter-room pathfinding, and no occlusion problems.** Characters never need to leave their room, so the hardest part of isometric rendering simply doesn't arise.

```
        ╔═══════════════════════════════════════════════════════════════════╗
        ║ OFFICE   LIVE FEED   APPROVALS   CONTROL CENTER   ▶ ▶▶ ▶▶▶ ⏸     ║
        ╠═══════════════════════════════════════════════════════╦═══════════╣
        ║                                                       ║ SYSTEM LOG║
        ║   ◆─────────◆            ◆─────────◆                  ║           ║
        ║  ╱ CEO      ╱           ╱ MANAGERS ╱                  ║ [09:15]   ║
        ║ ◆ OFFICE   ◆           ◆──────────◆                   ║ Rahul req…║
        ║  ╲        ╱   ◆══════════════════════════◆            ║           ║
        ║   ◆──────◆   ╱    DEVELOPMENT FLOOR      ╱            ║ [09:21]   ║
        ║             ◆                           ◆             ║ BLOCKED   ║
        ║  ◆───────◆   ╲   ▣  ▣  ▣  ▣  ▣  ▣     ╱              ║ by Gate 2 ║
        ║ ╱ DEVOPS ╱     ◆═══════════════════════◆              ║           ║
        ║◆─────────◆                                            ║ [09:25]   ║
        ║       ◆──────────────◆                                ║ Ben review║
        ║      ╱  MEETING ROOM ╱                                ║           ║
        ║     ◆───────────────◆                                 ║           ║
        ║  [−][+][fit]     ● working ● waiting ● blocked ● idle ║           ║
        ╚═══════════════════════════════════════════════════════╩═══════════╝
```

Palette comes from `04-UI-UX-BRIEF.md §2` — the office uses the same four signal colours as the console. That shared palette is the whole point: the amber halo over an avatar and the amber `REVIEW` chip in the event table are the same amber.

---

## 2. Projection & Coordinates

Standard 2:1 isometric.

```typescript
export const TILE_W = 64          // diamond width in px
export const TILE_H = 32          // diamond height in px
export const MAP_W  = 48          // tiles
export const MAP_H  = 40          // tiles

export function tileToWorld(tx: number, ty: number) {
  return {
    x: (tx - ty) * (TILE_W / 2),
    y: (tx + ty) * (TILE_H / 2),
  }
}

export function worldToTile(wx: number, wy: number) {
  return {
    tx: Math.floor((wx / (TILE_W / 2) + wy / (TILE_H / 2)) / 2),
    ty: Math.floor((wy / (TILE_H / 2) - wx / (TILE_W / 2)) / 2),
  }
}

// Depth sorting — the only correct rule for 2:1 iso with tall sprites
export function depthFor(tx: number, ty: number, layer = 0) {
  return (tx + ty) * 10 + layer      // layer: 0 floor, 1 furniture, 2 actor, 3 hud
}
```

Everything positioned in the scene sets `sprite.setDepth(depthFor(tx, ty, layer))`. Get this wrong and characters render behind desks they're sitting at.

Rendering must be crisp: `pixelArt: true` in the Phaser config, `image-rendering: pixelated` on the canvas (already in `globals.css`), and camera zoom snapped to `0.5 / 0.75 / 1 / 1.5 / 2` only — fractional zoom on pixel art produces shimmer.

---

## 3. The Floor Plan

Five rooms, defined as axis-aligned tile rectangles. Gaps between them are simply unpainted background.

| Room | Origin (tx,ty) | Size (w×h) | Capacity | Occupants |
|---|---|---|---|---|
| `ceo_office` | (2, 2) | 10 × 8 | 1 | emp_001 |
| `managers` | (16, 1) | 12 × 7 | 3 | emp_002, emp_003, + 1 spare desk |
| `dev_floor` | (26, 5) | 20 × 22 | 13 | emp_004 … emp_018, minus those elsewhere |
| `devops` | (1, 13) | 11 × 8 | 1 | emp_019 |
| `meeting_room` | (5, 24) | 16 × 12 | 8 (no fixed desks) | transient |

Desk assignment is deterministic: `sim/seed.py` writes `desk: (tx, ty)` onto each employee at seed time, and the office reads it. The renderer never decides where anyone sits — that would break rehydration.

### Room definition file

`apps/web/public/assets/office/office-map.json` (Tiled-compatible, hand-written is fine):

```json
{
  "tileWidth": 64, "tileHeight": 32, "width": 48, "height": 40,
  "rooms": [
    {
      "id": "dev_floor", "label": "DEVELOPMENT FLOOR",
      "origin": [26, 5], "size": [20, 22],
      "floorTile": "floor_grey",
      "walls": { "back": "brick_ne", "left": "brick_nw" },
      "labelAnchor": [36, 14],
      "furniture": [
        { "type": "desk_e",     "at": [28, 8] },
        { "type": "chair_e",    "at": [29, 8] },
        { "type": "monitor",    "at": [28, 8] },
        { "type": "partition",  "at": [28, 9] },
        { "type": "water_cooler","at": [44, 6] },
        { "type": "coffee",     "at": [45, 7] },
        { "type": "plant_tall", "at": [27, 25] }
      ],
      "desks": [
        { "slot": "d01", "at": [28, 8],  "facing": "e" },
        { "slot": "d02", "at": [31, 8],  "facing": "e" },
        { "slot": "d03", "at": [34, 8],  "facing": "e" }
      ]
    }
  ]
}
```

The `desks[].slot` ids are the contract between the seed script and the renderer. `seed.py` assigns `emp_007 → dev_floor/d02`; the renderer looks up the slot and gets both the tile and the facing.

---

## 4. Assets

### 4.1 What is needed

| File | Content | Frame size | Notes |
|---|---|---|---|
| `tileset.png` | 24 tiles | 64 × 64 (32px of overhang above the 64×32 diamond, for walls and tall objects) | one atlas, power-of-two canvas |
| `characters.png` | 8 base characters × 32 frames | 32 × 48 | walk/idle/type × 4 directions |
| `hud.png` | badge glyphs, halo rings, bubble tails | 16 × 16 | |
| `office-map.json` | the floor plan above | — | |
| `characters.json` | Phaser atlas frame map | — | generated by TexturePacker or written by hand |

**Tile list (24):** `floor_grey`, `floor_wood`, `floor_carpet_red`, `brick_nw`, `brick_ne`, `wall_cap`, `window_ne`, `desk_n/e/s/w`, `chair_n/e/s/w`, `monitor`, `partition`, `bookshelf`, `plant_tall`, `plant_small`, `water_cooler`, `coffee`, `whiteboard`, `server_rack`, `printer`, `meeting_table`.

**Character animations (per base sprite):**

| Key | Frames | Rate | Loop |
|---|---|---|---|
| `idle_{n,e,s,w}` | 2 | 2 fps | yes |
| `walk_{n,e,s,w}` | 4 | 8 fps | yes |
| `type_{n,e,s,w}` | 2 | 6 fps | yes |

That's 8 × 4 = 32 frames per character. Eight base sprites cover twenty employees; variety comes from Phaser `setTint()` on a shirt-colour palette of 6 values assigned deterministically from the employee id hash. Tint is applied to the whole sprite, so the base art should keep skin and hair in tones that survive a light tint — or, better, split the sprite into a base layer and a tintable shirt layer stacked as two sprites with the same depth. Do the two-layer version only if time allows; single-sprite tint is acceptable.

### 4.2 Sourcing — read this before downloading anything

The reference screenshot's style closely resembles commercial pixel-art interior packs. **Do not ship art you haven't licensed**, and don't assume a pack found on a search result is free.

| Route | Licence | Notes |
|---|---|---|
| **Kenney asset packs** (`kenney.nl`) — *Isometric Miniature Library*, *Isometric City*, *Tiny Town* | CC0, no attribution required | Safest default. Style is cleaner and less detailed than the reference; accept that. |
| **OpenGameArt**, filtered to CC0 / CC-BY | varies per asset — check each | Attribution file required for CC-BY; keep `CREDITS.md` from day one |
| **itch.io interior packs** (e.g. LimeZu *Modern Interiors*) | commercial, paid | Closest to the reference look. If you want this look, buy the licence and record it in `CREDITS.md`. A hackathon is not a licence exemption. |
| **Commission or generate your own** | yours | Slowest, fully safe, and gives you the exact rooms you need |

Whichever route: create `apps/web/public/assets/office/CREDITS.md` with source, author, licence and URL for every asset **as you add it**, not at the end.

### 4.3 Placeholder path (build this first, on day one of the visual phase)

Do not block the scene on art. Ship a placeholder atlas generated by a script:

```bash
python infra/scripts/make_placeholder_atlas.py
# writes tileset.png (flat-coloured diamonds + simple box furniture)
#        characters.png (32×48 coloured rectangles with a head dot, 4 facings)
```

Everything in §5–§10 works with placeholders. Real art drops in by replacing two PNGs and one JSON, with zero code change. Build the system against placeholders, swap art last.

---

## 5. Scene Structure

```
apps/web/src/game/
├── config.ts               Phaser.Types.Core.GameConfig
├── PhaserGame.tsx          React mount boundary (02-TRD §5.7)
├── bridge.ts               Zustand → scene event pump
├── scenes/
│   ├── BootScene.ts        loads atlases + map, shows the load bar, → OfficeScene
│   ├── OfficeScene.ts      floor, furniture, avatars, camera, input
│   └── HudScene.ts         name plates, badges, bubbles, room labels (screen-space)
├── entities/
│   ├── Avatar.ts           sprite + FSM + tween queue
│   ├── StatusBadge.ts      halo ring + glyph, pooled
│   ├── SpeechBubble.ts     short text over a head, pooled, auto-expires
│   └── DeskZone.ts         click target + seat anchor
└── systems/
    ├── AvatarFSM.ts        the state machine in §7
    ├── Pathfinder.ts       in-room A* on a small walkable grid
    ├── EventQueue.ts       bounded queue + coalescing
    └── CameraRig.ts        pan, clamp, snap-zoom, tween-to-avatar
```

### config.ts

```typescript
export const gameConfig: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,                    // WEBGL preferred, CANVAS fallback
  backgroundColor: '#080D16',           // --color-ink-950
  pixelArt: true,
  roundPixels: true,
  antialias: false,
  scale: { mode: Phaser.Scale.RESIZE, autoCenter: Phaser.Scale.NO_CENTER },
  fps: { target: 60, forceSetTimeOut: false },
  render: { powerPreference: 'low-power' },
  scene: [BootScene, OfficeScene, HudScene],
}
```

**Two scenes, deliberately.** `OfficeScene` is world-space and moves with the camera. `HudScene` is screen-space and does not — name plates, status pills and bubbles stay crisp and constant-size at every zoom level, which is why they read at 0.5× when the whole floor is visible. `HudScene` asks `OfficeScene` for each avatar's screen position once per frame and positions its own elements there.

---

## 6. Rendering the Floor

Drawn once at boot, never per frame:

```typescript
// OfficeScene.create()
const rt = this.add.renderTexture(0, 0, worldWidth, worldHeight).setOrigin(0)

for (const room of map.rooms) {
  // 1. back walls, painted first (highest ty first so they layer correctly)
  for (let i = 0; i < room.size[0]; i++) drawTile(rt, room.origin[0] + i, room.origin[1] - 1, room.walls.back)
  for (let j = 0; j < room.size[1]; j++) drawTile(rt, room.origin[0] - 1, room.origin[1] + j, room.walls.left)

  // 2. floor
  for (let i = 0; i < room.size[0]; i++)
    for (let j = 0; j < room.size[1]; j++)
      drawTile(rt, room.origin[0] + i, room.origin[1] + j, room.floorTile)
}
rt.setDepth(0)

// 3. furniture — real sprites, because they need depth sorting against avatars
for (const room of map.rooms)
  for (const f of room.furniture) {
    const { x, y } = tileToWorld(f.at[0], f.at[1])
    this.add.image(x, y, 'tiles', f.type)
        .setOrigin(0.5, 1)
        .setDepth(depthFor(f.at[0], f.at[1], 1))
  }
```

Walls and floors are flattened into one `RenderTexture` — roughly 1 800 tiles collapse to a single draw call. Furniture stays as individual sprites (about 90 of them) because avatars must be able to render in front of and behind them.

**Room labels** live in `HudScene` as `font-pixel` text at `labelAnchor`, at 55% opacity, so they read as floor markings rather than UI.

---

## 7. Avatars and the State Machine

### 7.1 Visual states

| State | Sprite | Badge | Halo | Name plate |
|---|---|---|---|---|
| `idle` | `idle_{facing}` | none | none | dim |
| `walking` | `walk_{facing}` | none | none | dim |
| `working` | `type_{facing}` | `●` in `allow` | soft green ring, 12% opacity | normal |
| `waiting` | `idle_{facing}` | `⏳` in `review` | amber ring, pulsing 1.4 s | normal + `Waiting approval` pill |
| `blocked` | `idle_{facing}` | `✕` in `block` | red ring, one flash then steady | normal + `BLOCKED` pill |
| `anomaly` | current sprite unchanged | `◆` in `anomaly` | magenta ring, slow 2 s pulse | normal + risk number |
| `meeting` | `idle_{facing}` | none | none | dim |

`anomaly` is an **overlay**, not a state — an employee can be `working` and flagged simultaneously. That distinction matters: the ML flagging someone who is visibly working normally is the most interesting thing the demo can show.

### 7.2 The FSM

```
                  ┌────────┐
        ┌────────►│  IDLE  │◄───────────────────────┐
        │         └───┬────┘                        │
        │             │ task.requested              │
        │             ▼                             │
        │        ┌─────────┐  gate1.block           │
        │        │ WALKING │  ────────────────┐     │
        │        └────┬────┘                  │     │
        │             │ arrived at desk       │     │
        │             ▼                       ▼     │
        │        ┌─────────┐            ┌─────────┐ │
        │        │ WORKING │◄───────────┤ BLOCKED │ │
        │        └────┬────┘  approved  └────┬────┘ │
        │             │ approval.requested   │      │
        │             ▼                      │ 4 s  │
        │        ┌─────────┐ denied/expired  │      │
        │        │ WAITING ├─────────────────┘      │
        │        └────┬────┘                        │
        │             │ task.completed              │
        └─────────────┴─────────────────────────────┘

  MEETING is entered only by a scenario script event (sim.meeting.started)
  and exited on sim.meeting.ended. It is purely cosmetic.
```

Transitions are driven **only** by events from `EventQueue`. Timed self-transitions exist for exactly two things: `BLOCKED → IDLE` after 4 seconds of wall time (so the floor doesn't fill with permanent red), and `WALKING → WORKING` on tween completion.

### 7.3 Movement

Movement is cosmetic and cheap:

- On `task.requested` while away from the desk, walk back to the desk.
- On `sim.meeting.started`, walk to a free meeting-room tile.
- Otherwise, a 6% chance per simulated hour of a short idle stroll to a water cooler or coffee tile and back.

Pathfinding is **A\* on the room's own small walkable grid** (at most 20 × 22 cells), never across rooms. A character's room never changes except for meetings, which teleport with a fade when the path would cross the gap:

```typescript
// systems/Pathfinder.ts — intentionally small
findPath(room: Room, from: Tile, to: Tile): Tile[]   // 4-directional, blocked tiles = furniture
```

Walk tween: `Phaser.Math.Distance` / `speed` where `speed = 90 px/s` at 1× and `180 px/s` at 10×. At 100× the office is not animating at all (§9).

If a path can't be found, the avatar teleports with a 150 ms fade. Nobody watching a demo will notice; a stuck character is far worse than a teleport.

---

## 8. The Event Pump

This is the component most likely to be got wrong. The office must never subscribe to the WebSocket, and must never render one DOM/scene update per event.

```typescript
// game/bridge.ts
export function startBridge(game: Phaser.Game, onSelect: (id: string) => void) {
  const queue = new EventQueue({ max: 400 })          // bounded, drops oldest
  const unsub = useTelemetry.subscribe(
    (s) => s.officeQueue,                             // a slice, not the whole stream
    (events) => queue.pushAll(events)
  )

  let raf = 0
  const pump = () => {
    const scene = game.scene.getScene('OfficeScene') as OfficeScene
    if (scene?.ready) {
      // Budget: at most 12 events per frame. Anything more is invisible anyway.
      for (const e of queue.drain(12)) scene.applyEvent(e)
    }
    raf = requestAnimationFrame(pump)
  }
  raf = requestAnimationFrame(pump)

  return { stop() { cancelAnimationFrame(raf); unsub() } }
}
```

### 8.1 Which events the office cares about

Only six of the fourteen. Everything else is ignored by the renderer (it still reaches the Live Feed).

| Event | Effect on the office |
|---|---|
| `task.requested` | avatar → `WALKING` (if away) then `WORKING`; bubble with the task title, 4 s |
| `gate1.decision` | `block` → `BLOCKED`; `review` → `WAITING`; `redact` → brief `redact`-coloured spark over the head; `allow` → no change |
| `gate2.decision` | `block` → `BLOCKED` + shake 200 ms; `review` → `WAITING` + manager's avatar gets a bell badge |
| `approval.decided` | approved → `WORKING`, one green flash; denied/expired → `BLOCKED` |
| `task.completed` | → `IDLE` after a 1 s hold |
| `risk.updated` | if `score >= 70`, apply the `anomaly` overlay; if it drops below 60, remove it |

Any event whose `employee_id` is unknown to the scene is silently discarded (it can happen after a run switch).

### 8.2 Coalescing

At 10× the server already batches WS frames into 250 ms groups. The pump adds a second guard: if more than one event for the same employee lands in a single drain, only the last one is applied, except for `BLOCKED`, which always wins and always animates — a block that flickers past invisibly defeats the purpose of the whole view.

### 8.3 Snapshot and reconciliation

```typescript
async function resnapshot(runId: string) {
  const snap = await api.get<OfficeSnapshot>(`/sim/runs/${runId}/state`)
  scene.applySnapshot(snap)                    // positions, fsm, badges — no animation
  useTelemetry.getState().setLastSeq(snap.seq) // stream resumes after this
  queue.clear()
}
```

Called on: mount, WebSocket reconnect where `gap > 500`, exit from 100× mode, and run switch. `applySnapshot` sets state directly with no tweens — it is a hard cut, deliberately, because an animated catch-up would be a lie about what happened.

---

## 9. Speed Modes

| Speed | Office behaviour |
|---|---|
| **Paused** | Animations stop (`scene.anims.pauseAll()`), canvas dims to 60%, centred `PAUSED` pixel chip. Camera still pans; clicking still opens drawers. |
| **1× real time** | Everything as specified. Walk tweens, bubbles, badge transitions, idle strolls. |
| **10×** | Walk speed doubles (not 10×'d — that looks like a bug). Idle strolls disabled. Bubbles shortened to 1.5 s. Badge transitions keep full duration; they're the information. |
| **100× fast-forward** | The canvas is **replaced**, not sped up. `OfficeScene` pauses; the fast-forward overlay from `03-APP-FLOW.md §7.1` takes the space. On completion → `resnapshot()` → the office reappears at the new sim time. |

Rendering 100× as motion would produce an unreadable strobe and would drop frames. Replacing it with a progress meter and a summary card is both more honest and more impressive.

---

## 10. HUD Details

### 10.1 Name plate

Screen-space, anchored 52px above the avatar's feet, follows every frame.

```
┌──────────────────────────┐
│ ● Rahul │ Engineer  🖵   │      ● = status dot (signal colour)
└──────────────────────────┘      🖵 = agent brand glyph
```

- Background `rgba(13,20,32,0.88)`, 1px `--color-line` border, `--radius-none` (pixel surfaces stay sharp)
- Name in `font-pixel 11px`, role in `font-pixel 10px` at `--color-text-dim`
- Dims to 45% opacity when `idle`, full opacity otherwise
- Hidden entirely below camera zoom 0.6 (unreadable anyway), replaced by the status dot alone

### 10.2 Status pill

Rendered beside the plate only for `waiting`, `blocked` and `anomaly`:

```
 ⏳ Waiting Approval        amber fill at 18%, amber 1px border, amber text
 ✕  BLOCKED                 red fill at 18%, red border, red text
 ◆  Risk 84                 magenta, appears only with the anomaly overlay
```

### 10.3 Click card

Clicking an avatar does two things: opens the React employee drawer (`03-APP-FLOW.md §5`) and shows a small in-canvas card next to the sprite for 6 s, matching the reference screenshot:

```
┌────────────────────────────────┐
│ ⚠ Rahul                        │
│   Engineering Intern           │
├────────────────────────────────┤
│ WAITING FOR APPROVAL           │
│ Agent attempted production     │
│ deployment.                    │
└────────────────────────────────┘
```

The card is `HudScene` content, `font-pixel`, positioned to stay inside the viewport (flips to the left side near the right edge).

### 10.4 Speech bubbles

Short, 4 s, max 28 characters, one per avatar at a time, pooled (8 instances reused). Text comes from the task title or the policy message, truncated with an ellipsis. Suppressed entirely at 10× when more than 6 are queued.

### 10.5 Manager bell

When an approval request is routed to a manager, that manager's avatar gets a `🔔` badge with a count, pulsing once per arrival. Clicking it navigates to `/approvals`. This is the visual link between the floor and the queue, and it's worth getting right — it's the moment in the demo where the two halves of the product connect.

### 10.6 Reduced motion

With `prefers-reduced-motion: reduce`, the scene: disables walk tweens (teleport with a fade), disables idle bobbing and strolls, disables halo pulsing (static rings instead), and keeps badge and colour changes at full fidelity. State is never hidden by an accessibility setting.

---

## 11. Fallback: the Card Grid

Required, not optional. It covers three real cases: WebGL unavailable, the snapshot failing, and the visual phase running out of time.

```
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ ⬛ Rahul S. │ │ ⬛ Priya S. │ │ ⬛ Nikhil R.│ │ ⬛ Mark D.  │
│ Intern     │ │ Engineer   │ │ Engineer   │ │ DevOps     │
│ Payments   │ │ Payments   │ │ Platform   │ │ Platform   │
│            │ │            │ │            │ │            │
│ ⏳ Waiting  │ │ ● Working  │ │ ● Working  │ │ ○ Idle     │
│ risk ██ 61 │ │ risk █  22 │ │ risk ███ 84│ │ risk █  38 │
│            │ │            │ │      ◆ flag│ │            │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
```

- Pure React, no canvas: `components/office/AvatarGrid.tsx`
- 4–5 columns, cards use the interactive-card style from `04-UI-UX-BRIEF.md §5.4`
- Reads the identical `simStore` avatar state, so it stays in sync with no extra wiring
- Fully keyboard navigable; this is the accessible path to the office
- Reachable deliberately via a `Simple view` toggle in the office toolbar — not only as an error state

Build this **before** the Phaser scene. It takes two hours, it de-risks the entire visual phase, and it proves the store shape is right before any game code exists.

---

## 12. Performance Budget

| Metric | Target | How |
|---|---|---|
| Frame rate, 20 avatars, 1× | ≥ 58 fps | flattened floor RenderTexture; one texture atlas; tweens not per-frame math |
| Frame rate, 10× | ≥ 50 fps | event budget of 12 per frame; bubbles suppressed under load |
| Draw calls | < 120 | single atlas for tiles + characters; HUD in its own scene batches separately |
| Texture memory | < 16 MB | atlases ≤ 2048×2048, no mipmaps, `pixelArt: true` |
| Boot to interactive | < 1.2 s | atlas ≤ 400 KB, map JSON ≤ 40 KB, no runtime tile generation |
| Memory after 10 min at 10× | < 180 MB | pooled badges and bubbles; bounded event queue; no listener accumulation |

**Profiling checkpoints.** After building the scene, open Chrome Performance and confirm: no allocation sawtooth (means something is created per frame), no layout thrash from the HUD (it must use `transform`, never `top`/`left`), and Phaser's `game.loop.actualFps` steady above target with the Live Feed open in another tab.

**The three classic mistakes here**, all of which will happen if not guarded against:

1. Creating a new text object per name-plate update instead of calling `setText`. Pool everything.
2. Subscribing to the Zustand store per avatar. Twenty subscriptions × 200 events/sec is 4 000 React updates/sec. One pump, one subscription.
3. Sorting the display list every frame. Depths are set on placement and only change when an avatar moves — `scene.children.depthSort()` is not needed per frame.

---

## 13. Build Order for the Visual Phase

Half-day increments. Each step is shippable on its own.

| Step | Output | Time |
|---|---|---|
| V0 | `AvatarGrid` fallback, wired to `simStore` | 2 h |
| V1 | Placeholder atlas script; Phaser boots; floor renders; camera pans and zooms | 2 h |
| V2 | Twenty avatars at seeded desks; idle animation; depth sorting correct | 2 h |
| V3 | `HudScene`: name plates, status dots, room labels | 1.5 h |
| V4 | Event pump; the six events change badges and states | 2 h |
| V5 | Click → employee drawer; click card; camera tween to avatar | 1.5 h |
| V6 | Walking, bubbles, manager bell, blocked shake | 2 h |
| V7 | Snapshot / rehydration / 100× overlay handoff | 1.5 h |
| V8 | Real art swapped in; `CREDITS.md`; polish pass | 2 h |

**Cut line: V5.** With V0–V5 done, the office is fully demo-capable — characters at desks, live status, clickable detail. V6–V8 are the parts people remember, and they are also the parts to sacrifice if Phase 7 (risk) slipped. Cutting V6–V8 costs charm; cutting Phase 7 costs the product's thesis.

---

## 14. Acceptance Checklist

- [ ] 20 avatars render at their seeded desks, with correct depth against furniture
- [ ] `game.loop.actualFps ≥ 50` with 20 avatars at 10× on integrated graphics
- [ ] A `gate2.decision` with `decision=block` turns the right avatar red within 500 ms of the event arriving
- [ ] An approval routed to Ben puts a bell on Ben's avatar, and approving from `/approvals` clears it and turns the requester green
- [ ] Clicking any avatar opens the drawer and pans the camera; `Esc` closes it
- [ ] Page reload mid-run restores every avatar's exact state with no visual desync against the Live Feed
- [ ] Switching to 100× replaces the canvas; returning resnapshots correctly
- [ ] `prefers-reduced-motion` removes tweens and pulsing but keeps every state change
- [ ] Canvas `aria-label` updates every 2 s with a headcount by status
- [ ] `Simple view` toggle switches to the card grid and back without losing state
- [ ] Forcing `type: Phaser.CANVAS` still renders correctly (WebGL is not assumed)
- [ ] `CREDITS.md` lists a source and licence for every shipped asset
- [ ] `grep -rn "fetch\|axios\|WebSocket" src/game/` returns nothing
