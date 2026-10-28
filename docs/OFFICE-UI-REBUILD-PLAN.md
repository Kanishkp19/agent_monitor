# Office UI: recommended direction and delivery plan

Date: 2026-10-27. First development-floor preview implemented; verification
and remaining acceptance limits are recorded in `CURRENT.md` and
`office-rebuild-evidence/`. Five-room expansion has not started.

## Decision

Rebuild the office presentation incrementally, preserving the application, telemetry/store integration, employee inspection, and reusable navigation logic. Start with one representative development-floor section. Expand only once its art, depth, movement, and readable status UI work together.

A camera/CSS repair can improve readability quickly, but cannot solve the current flat-room rendering constraint. A complete application rewrite would discard useful integration and add unnecessary scope. The recommended middle path replaces the scene composition and asset pipeline, then adapts existing behavior where verified.

## What the reference requires

Treat the first attachment as the current visual and the second as the intended direction. The target is a people-first, cutaway isometric office: large recognizable employees, consistent furniture proportions, connected rooms, clear working/waiting/blocked states, and details available on selection. Match these properties rather than reproducing every pixel or permanently displaying every label in the reference.

The current screenshot emphasizes the building and furniture; employees and labels are too small to explain activity at a glance. The target emphasizes people, tasks, and status. Enlarging the current sprites alone would leave inconsistent seating and furniture relationships.

## Evidence from the current implementation

- `apps/web/src/game/engine/WorldRenderer.ts:28` defines five rooms; lines 65–77 describe calibration of separately rendered room images into a common projection. Existing room layout comments also disagree with some current dimensions, so source data needs consolidation.
- `apps/web/src/game/OfficeSimulation.tsx:555` draws all room images before the employee pass. Employees are depth-sorted against each other, not against individual desks or walls. Correct furniture occlusion requires separate foreground layers or independently rendered props.
- `apps/web/src/game/engine/PersonRenderer.ts:239` draws atlas frames at their native size with a foot anchor. Character proportions must be designed alongside desks and chairs, not patched with unrelated per-room scaling.
- `apps/web/src/game/OfficeSimulation.tsx:300` hides plates below zoom 0.35 and otherwise places them at fixed screen offsets. This explains a readability risk at overview scale; it does not establish the exact zoom of the supplied screenshot.
- `apps/web/src/game/engine/Furniture.ts` maintains collision footprints and activity points separately from the painted scene. Navigation already exists, but visual alignment depends on calibration.
- `apps/web/src/game/OfficeSimulation.tsx` consumes `useSim`, while the route retains surrounding controls. Preserve this boundary: visual movement must not decide policy outcomes.
- Existing focused tests cover navigation and office isolation. They do not establish visual correctness.

Assessment limits: source and supplied screenshots inspected; no live browser reproduction or performance measurement performed. The graph service does not index this repository. The working tree already has substantial uncommitted changes; implementation must preserve them. No external framework/version recommendation is needed for this plan.

## Options

| Option | Benefit | Limitation | Decision |
| --- | --- | --- | --- |
| Repair camera, labels, sprite scale | Fast improvement to the existing scene | Flat furnished images still limit occlusion and seating; calibration remains fragile | Useful only as a temporary improvement |
| Rebuild office presentation in stages | Addresses visual structure while retaining working integrations | Requires cohesive assets and a scene model | Recommended |
| Rewrite the entire app or switch rendering engines immediately | Maximum freedom | More integration risk; engine choice alone does not fix art or composition | Not justified by current evidence |

## Delivery sequence

### 1. Establish the baseline and art contract

Run the current office harness and application route with deterministic employee fixtures. Capture overview, desk close-up, selection, and working/waiting/blocked states. Record clipping, missing assets, movement problems, and actual frame timing separately from screenshot observations.

Define one projection, tile unit, character height, foot anchor, desk/chair proportions, wall height, palette, lighting direction, and pixel-density policy. Produce a single desk-group composition before authoring the whole map. Specify standing, walking, typing, and seated poses with matching directions. Choose or create cohesive assets with recorded provenance; avoid combining unrelated room paintings and sprite styles.

Exit: the desk group is readable at its intended default viewport scale and its standing/seated characters fit the furniture.

### 2. Build one complete development-floor section

Create a small data-driven scene containing two desk clusters, a doorway, a short corridor, and a break point. Store room bounds, prop positions, collision shapes, seat anchors, facing, and interaction points in one authoritative scene definition. Derive navigation data from it.

Keep the current Canvas renderer initially. Cache static floor/background layers; render characters and occluding furniture using explicit depth anchors and split foreground pieces where a single depth value is insufficient. Cut away or fade obstructing foreground walls. Do not bake interactive desks, chairs, or foreground walls into a single room image.

Exit: a person can walk behind and in front of a desk, pass through the door, and sit correctly without clipping or appearing on top of furniture. This is the first implementation milestone and the decision point for expanding the approach.

### 3. Make the office understandable as an interface

Provide separate overview and focused-room camera framing, pan/zoom limits, fit-to-view, and employee focus. At overview scale show room summaries and critical alerts; at closer scale show names and individual states. Prioritize selected, blocked, and waiting employees, avoid label overlap, and clamp inspection cards to the viewport.

Keep labels in screen space with readable type. Use text/icons as well as color. Support keyboard employee selection and focus, reduced motion, and the existing simple employee view. Preserve selection and drawer behavior across view changes.

Exit: users can find a blocked employee, inspect the reason, and return to the overview without losing context or encountering offscreen controls.

### 4. Integrate believable behavior with real state

Reuse navigation and motion only after confirming them against the new scene. Add seat reservation, explicit doorway connectivity, destination facing, arrival/typing/seated transitions, and restrained ambient activity. Verify spawn locations and unreachable destinations. Avoid visible teleportation during normal operation; define a controlled recovery when state or layout changes invalidate a route.

Keep backend task/policy state authoritative. Ambient walking and coffee breaks are presentation behavior. Verify initial snapshots, employee additions/removals, reconnects, pause/resume, accelerated playback, and selected-employee updates. Clearly separate demo fixtures from live data.

Exit: scripted state changes produce the correct badges, details, and animations; decorative activity cannot fabricate a task completion or approval.

### 5. Expand the validated system to five rooms

Build the development floor, meeting room, managers area, CEO office, and DevOps room from the same visual kit. Establish clear entrances and shared circulation. Use furniture density and floor treatment to distinguish rooms while preserving scale. Add meeting seating and server-area interactions only after the basic desk behavior is stable.

Exit: every intended destination is reachable, seats are correctly aligned, and all rooms remain legible at overview and focus scales.

### 6. Verify, then replace the current view

Keep the new scene behind a temporary development toggle until visual and interaction checks pass. Compare it with the old view using the same fixtures. Remove superseded paths only after the new route is validated, and update the stale Phaser-oriented game README to describe the actual implementation.

Exit: targeted tests and visual review pass; preserve a straightforward rollback during the transition.

## Acceptance criteria replacing “flawless”

- Consistent projection, character/furniture scale, lighting, and anchors across all five rooms.
- No observed desk/wall clipping, incorrect draw order, or blocked intended routes in the scripted movement scenarios.
- Working, waiting, blocked, selected, and disconnected states remain distinguishable and truthful.
- No overlapping priority labels or offscreen inspection cards at representative 1280×720, 1440×900, and 1920×1080 desktop viewports; smaller widths retain usable simple-view access.
- Keyboard selection, reduced motion, pan, zoom, fit, drawer opening, pause/resume, and reconnect work in focused checks.
- Target smooth 60 fps on an agreed reference desktop with the full employee fixture; record actual frame timings before calling this achieved. Verify no steadily increasing memory after repeated mount/unmount and an extended scene run.
- Missing art or unavailable telemetry produces a clear recoverable state.

## Targeted verification during implementation

Run the existing navigation and office-isolation tests first. Add focused checks for scene connectivity, valid seat anchors, depth ordering, screen/world hit testing, and telemetry-to-visual transitions where behavior changes. Use deterministic screenshots for occlusion, seated alignment, overview density, and HUD clipping. Run web typecheck after code changes. Avoid the full test suite unless explicitly requested.

## Scope and risks

The main dependency is a coherent set of layered assets; a rendering-library migration cannot substitute for that. If the existing art cannot be separated cleanly, replace it room by room. Keep the single-room milestone bounded before committing to full asset production. Estimate calendar effort after this milestone reveals asset production cost and remaining integration defects.

First implementation slice: baseline captures plus the two-desk development-floor section with one walking/seated employee, correct occlusion, and one live-state badge. Do not begin a full five-room rebuild until this slice meets its exit criteria.
