# Current slice: Public Autopilot preview (2026-10-30)

Scope: publish a free public preview from this Docker host with only the
token-protected Autopilot API reachable through the web proxy. Remove the
hard-coded UI token and rotate the local demo token before exposure.
Files: `apps/web/src/routes/autopilot.tsx`, a separate public Vite config,
this status file; ignored `services/api/.env` token changes locally.
Checks: web typecheck; public route and API allow/block HTTP probes; live
authorized fixture request through the public URL; verify other API routes are
not proxied. Status: complete. Public browser loaded the page, accepted the
rotated token, and displayed three fixtures. Other API POST routes return 404
at the public proxy; unauthenticated Autopilot configuration returns 401.
Ngrok URL: https://adduceable-farraginous-cedrick.ngrok-free.dev/autopilot .
The host must remain awake and the API, Vite, Docker, and tunnel running.

# Submission verification (2026-10-30)

The live Nebius smoke passed with the configured Nemotron 3.5 Lightning model
after increasing its text output cap to 512. Docker isolation checks passed.
The evaluator recorded 10/10 correct policy probes; buggy-auth and
regression-guard reached verified patches with passing after-tests. The
prompt-injection fixture failed twice on an invalid model `apply_patch` action;
no secret-read attempt or successful fix is claimed. Public results and a
Devpost draft are in `docs/DEVPOST-READY.md`. Public video and demo/test-build
URLs are still pending.

# Current slice: Restore redesigned office route

Scope: route the default office view to the existing ReferenceOffice redesign.
Cause: office.tsx still rendered the legacy OfficeSimulation despite the completed redesign.
Files: apps/web/src/routes/office.tsx; this status file.
Checks: web typecheck; focused reference scene/life/isolation tests; browser route smoke.
Status: complete. Canvas implementations and existing UI polish preserved.
Verification: typecheck and 12 focused reference scene/life/isolation tests pass.
Chrome at 1126x827 confirms redesigned route, room focus, Fit and log toggling,
with no horizontal overflow or page errors. Screenshot: ui-polish-evidence/office-restored.png.
Restarted the stale Vite server on port 5181; served module now imports ReferenceOffice.

# Previous slice: Console visual polish

Scope: shared dark-theme surfaces, navigation hierarchy, Autopilot evidence dashboard,
office action dock and employee drawer chrome. Preserve stores, API contracts and canvas.
Files: globals.css, AppShell.tsx, ui/index.tsx, EmployeeDrawer.tsx, autopilot.tsx, office.tsx.
Checks: web build, Autopilot Vitest, browser layout/interaction checks with mocked data.
Status: complete. Existing uncommitted work is preserved.
Verification: web production build and both focused Autopilot tests pass. Chrome
checks pass at 1024/1280/1440/1920px with no horizontal overflow. Mocked completed
job receipts, Copy Diff feedback, office navigation and system-log toggle pass;
no page errors. Screenshots: docs/ui-polish-evidence/. Preview: localhost:5181.
Limits: no live provider execution tested; existing missing Departure Mono font
and empty Phaser chunk build warnings remain. Canvas rendering is unchanged.
Graph lookup: this repository is not indexed; targeted source search used instead.

# Previous slice: Lively interactive office

Scope: decorative aisle strolls, desk gestures, waves, fixed chairs, ambient
coffee detail and keyboard camera controls. Preserve live telemetry and drawer.
Files: ReferenceOffice, ReferenceScene, new OfficeLife sampler, focused tests.
Checks: reference scene/life and office isolation tests, typecheck, targeted
browser movement/pause/reduced-motion and existing interaction checks.
Status: complete.

Verification: web typecheck passes; 12 focused tests pass (continuous room-bound
loops, protected work/wait/block poses, deterministic pause, seating, isolation).
Chrome checks pass for advancing animation, wave interaction, local/global pause,
reduced-motion freeze, all three viewports, labels, selection/drawer/Escape,
room camera and log controls. Screenshot: office-rebuild-evidence/office-life-wave.png.

Movement is decorative and keeps live task statuses unchanged. Idle employees
walk short aisle loops; working employees type; waiting/blocked employees stay
at their desks. Pause life and global Pause freeze animation; reduced motion
removes roaming. Arrow keys pan the focused canvas, 0 fits, double-click focuses
a room, and Wave hello triggers a brief group greeting. This is not a freely
navigable game or a cross-room pathfinding system. No sustained FPS claim.

# Previous slice: Reference-inspired five-room office

Scope (2026-10-27): user-requested replacement of the broken office composition.
Build one coherent brick-and-tile scene with correctly seated employees, readable
status labels, room focus, zoom, keyboard selection, and existing drawer integration.
Keep telemetry authoritative and preserve the existing preview and simple view.

Files: new ReferenceOffice component and ReferenceScene renderer, office route,
focused scene tests and browser check/evidence. Existing uncommitted work is preserved.
Targeted checks: reference-scene and office-isolation Vitest; web typecheck;
browser at 1280×720, 1440×900, 1920×1080, selection, camera and store transitions.
Status: complete for this reference-inspired office slice.

Verification: web typecheck passes; reference-scene + office-isolation pass
(9 tests). Browser checks pass at 1280×720, 1440×900 and 1920×1080 with
isolated store fixtures, collision-free badges, focus/zoom/fit, log toggle,
selection/drawer/Escape, keyboard controls, status/removal and empty telemetry.
No page errors. Screenshots and reference-check.json are in
`docs/office-rebuild-evidence/`. Scoped tracked-file whitespace check passes.

Preview: http://127.0.0.1:5174/office (polling-enabled Vite). Existing 5173
processes served cached modules, so verification used a fresh server.

Limits: original canvas illustration, not pixel-identical reference artwork.
This view displays assigned seats and live statuses; autonomous walking from
the older engine is not used. Twenty catalog seats plus four extension seats;
additional employees remain selectable as off-floor. Full remote drawer data,
live reconnect and sustained performance were not verified. Existing drawer
fallback data and unrelated changes are preserved.

# Previous slice: Office development-floor preview

Scope (2026-10-27): first slice of `OFFICE-UI-REBUILD-PLAN.md`: baseline
captures and one layered development-floor section. Preserve the existing
office, telemetry, drawer and simple view. No five-room rollout in this slice.

Files: `apps/web/src/game/DevelopmentFloor.tsx`,
`engine/DevelopmentScene.ts`, `engine/DevelopmentRenderer.ts`, focused scene
tests, preview harness, route toggle and visual evidence/check helper.

Targeted checks: navigation, development-scene and office-isolation Vitest
files; web typecheck; browser snapshots at 1280×720, 1440×900, 1920×1080;
keyboard selection, reduced motion, store transitions and preview rollback.

Status: first implementation slice complete as a development preview.

Verification (2026-10-27): navigation + development-scene + office isolation
pass (24 tests); web typecheck passes. Browser checks pass at all three
desktop sizes: fixture states, keyboard selection, viewport controls, reduced
motion, movement snapshots, store additions/status transitions/removals and
route preview/rollback. No page errors. Targeted tracked-file whitespace check
passes. Baseline harness/route and new screenshots plus machine-readable result
are in `docs/office-rebuild-evidence/`.

Remaining: coherent five-room kit, stable seating for all employees, focused
room camera/priority labels, live reconnect/pause scenarios and full drawer
data checks. This prototype shows four representative employees and an
explicitly requested decorative walking tour. It does not replace production.
No sustained frame timing, memory/leak test or 60fps acceptance claim. Compare
and approve the art direction before expanding per the rebuild plan.

## Previous slice: Autopilot offline readiness

Scope: credential preflight and API contracts, isolated runner smoke helper,
Autopilot dashboard feedback, MIT license, judge setup/disclosure and demo script.
Preserve existing work and simulator provider choices. No live inference without a key.

Targeted checks: Autopilot tests plus Nebius adapter contracts; API Ruff and strict
mypy; generated event contract consistency; web typecheck/build and focused route
tests; Docker smoke helper (requires installed Docker and a running daemon).

Status: implementation complete; Docker execution, live inference, and global
strict typing remain blocked as described below. No live success is claimed.

## Verification (2026-10-26)

- From `services/api`: `.venv/bin/python -m pytest tests -k autopilot -q`
  passed (33 tests; 133 deselected).
- Autopilot plus `tests/contract/test_nebius_llm_contract.py` and
  `tests/contract/test_llm_contract.py`: 74 tests passed after final code edits.
- Ten offline policy probes passed; measured results saved locally in
  `.data/autopilot-offline-probes.json`. No live jobs were invoked.
- API Ruff and the smoke helper pass. Scoped strict mypy passes for Autopilot,
  its API route, Nebius adapter, and helper (10 source files), using
  `--strict --follow-imports=silent` to keep imported unrelated modules outside
  this check.
- Both generated event outputs match `packages/contracts/events.schema.json`.
  OpenAPI route/cursor coverage and missing-key JSON responses pass API tests.
- From `apps/web`, `pnpm --config.verify-deps-before-run=false --filter web
  typecheck`, the matching `build`, and focused Vitest route tests pass (2 tests).
  The flag bypasses pnpm's automatic dependency reinstall in this npm-managed
  project. Build emits existing font-resolution and empty-Phaser-chunk warnings.

## Blockers / remaining work

- Docker CLI is absent. The smoke helper exits clearly with setup guidance;
  image build, real isolation/resource checks, exit receipts and timeout cleanup
  still need execution on a Docker host. Its resource assertions use cgroup v2.
- No live Nebius key is available: verify account model access and tool calling,
  all three live fixtures, and real reports before recording/submitting.
- Repository-wide strict mypy failed across unrelated simulator, AWS adapter,
  API and CLI files (including missing third-party stubs and existing typing
  errors). Fixed the Autopilot patch argument narrowing found by that run;
  broader fixes remain outside this slice. The global check is not green.
- Repository-wide `git diff --check` reports pre-existing whitespace in
  `docs/architecture.md`; targeted tracked-file whitespace checks pass.
- Public repository/demo/video URLs, final commit provenance, and live-use
  feedback remain submission actions. Existing work was preserved.
