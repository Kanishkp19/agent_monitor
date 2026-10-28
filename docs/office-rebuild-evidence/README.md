# Development floor evidence — 2026-10-27

Baseline: `baseline-harness.png` uses the existing deterministic catalog;
`baseline-route.png` records the app without a running API. The existing
room paintings draw before people, with disproportionately small characters.
The route baseline is an offline observation, not a successful live session.

New: `preview-1280x720.png`, `preview-1440x900.png`,
`preview-1920x1080.png`, `selected-blocked.png`, `behind-desk.png`,
`front-aisle.png`, `doorway.png`, `preview-route.png`.
All fixtures are explicitly labeled. The scene is original Canvas vector art;
it uses no external images or generated bitmap assets. No missing art requests
are required by the new preview. Rear walls stay behind the interior and the
front partition is deliberately cut away.

The browser check exercises the actual component, matching live-store updates
to working/blocked controls and removing avatars on a replacement snapshot.
It also verifies reduced motion, keyboard selection, viewport button bounds
and the route toggle back to the existing office. See `browser-check.json`.

Limits: movement screenshots sample scenarios; they are not an exhaustive
clipping proof. Priority-label layout currently reserves four fixed columns.
No sustained frame timing or extended mount/unmount memory test was performed.
Full employee counts, five-room assets, live reconnects and real drawer data
still need the later slices in the plan. The original screenshot attachments
are not present in this chat; visual direction follows the written contract.
