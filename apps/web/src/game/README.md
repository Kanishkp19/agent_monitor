# `src/game/` — Canvas office

The current office uses `OfficeSimulation.tsx`, `engine/WorldRenderer.ts`
and the navigation/motion/behavior modules. It reads `useSim` directly;
the Phaser modules described in the historical notes below were removed.

The first rebuild milestone is available in development at
`/office?scene=development` (or the **New floor preview** button). **Current
office** returns to the existing view. The employee query parameter survives
switching views; live selections still open the existing drawer. Simple view
continues to use the same store. The preview intentionally shows four employees.

`DevelopmentScene.ts` owns geometry, seat anchors, doorway and collision data.
`DevelopmentRenderer.ts` supplies an original Canvas vector kit, cached floor
and separate depth-sorted desks, monitors, chairs and people. No external art
or new asset license is involved. Art contract: 64×32 tiles, 48px standing
people, 26px tabletops, 72px rear walls, northwest lighting, muted daylight
palette; feet are the world anchor. Foreground partitions are cut away.

`/development-floor.html` mounts the same component without the API. Fixtures
require explicitly choosing **Try demo fixtures** and never write to the store
or open a real employee drawer. **Preview walk** starts a deterministic path
through the doorway and break point; policy/task states always come from the
store. Reduced motion disables that decorative walk. The walk follows pause
and speed state, capped at 3× for readable motion.

Focused checks: `npm test -- src/game/__tests__/navgrid.test.ts
src/game/__tests__/development-scene.test.ts src/__tests__/office-isolation.test.ts`
and `npm run typecheck`. With Vite running, `node scripts/verify-office-preview.mjs`
uses Playwright (or `PLAYWRIGHT_MODULE`) and installed Chrome to save evidence
under `docs/office-rebuild-evidence/`. Desktop acceptance and five-room
expansion remain separate from this preview; no sustained performance claim.

## Historical Phaser design notes

**Nothing in this directory may fetch.**

The office is a renderer over the telemetry stream, not a simulator. It reads
from the Zustand store through `bridge.ts` and has no other input. No `fetch`,
no `WebSocket`, no `axios`, no import of `@/lib/api`.

`src/__tests__/office-isolation.test.ts` asserts this, and it has asserted it
since before this directory had any code in it — a rule added after the first
violation is a rule that has already lost.

## The one rule

The office holds no truth. Closing the tab changes nothing. It cannot start,
stop, approve, block or schedule anything; it can only show what already
happened. If the canvas and the Live Feed ever disagree, **the Live Feed is
right** and the scene resnapshots.

Avatar position, walking and idle animation are decorative. No governed
outcome depends on where a character is standing — which is why a failed path
can safely teleport.

## Layout

```
config.ts          projection, depth rule, zoom steps, Phaser config
PhaserGame.tsx     the React mount boundary — deliberately tiny
bridge.ts          the event pump: one subscription, one RAF loop, 12/frame
scenes/
  BootScene.ts     atlases, animations, runtime fallbacks
  OfficeScene.ts   world-space: floor, furniture, avatars, camera, input
  HudScene.ts      screen-space: plates, pills, bubbles, aria-label
entities/
  Avatar.ts        sprite + halo + FSM state + tween queue
systems/
  AvatarFSM.ts     event -> visual transition
  Pathfinder.ts    in-room A* only; rooms never connect
  EventQueue.ts    bounded, coalescing, blocks always win
  CameraRig.ts     pan, clamp, snap-zoom, tween-to-avatar
```

Status badges and speech bubbles are **pooled objects inside `HudScene`**
rather than separate entity classes. Pooling is the requirement; a class per
glyph would have made it easier to forget.

## The three classic mistakes

All three will happen if they are not guarded against:

1. **A new text object per name-plate update.** Pool everything; call
   `setText`. This shows up as an allocation sawtooth in the performance panel
   about a minute in.
2. **A Zustand subscription per avatar.** Twenty avatars × 200 events/second is
   4,000 React updates a second. There is exactly one subscription, in
   `bridge.ts`.
3. **Sorting the display list every frame.** Depths are set on placement and
   only change when an avatar moves. `depthSort()` is never called per frame.

## Depth

Depth comes from `(tx + ty)`, never from world `y`:

```ts
depthFor(tx, ty, layer) // (tx + ty) * 10 + layer
```

Get this wrong and characters render behind the desks they are sitting at.

## Speeds

| Speed | Behaviour |
|---|---|
| Paused | Animations stop, canvas dims to 60%, camera still pans, clicks still work |
| 1× | Everything as specified |
| 10× | Walk speed **doubles**, not 10×s — 10× looks like a bug. Badge transitions keep full duration; they are the information. |
| 100× | The canvas is **replaced**, not sped up. A progress overlay takes the space, then the office resnapshots. |

Rendering 100× as motion would be an unreadable strobe and would drop frames.

## Build order

V0–V8 in `docs/07-OFFICE-SIMULATION.md` section 13. **The cut line is V5**: with
V0–V5 done the office is fully demo-capable. V6–V8 are the parts people
remember, and also the parts to sacrifice first.
