# Autopilot Scope — what is real, what is simulated, what is new

Updated 2026-10-26 after the Autopilot implementation. This records what is
implemented and what still requires live verification.

## Already real (unchanged, must keep working)

- **Governance core.** `governance/gate1.py`, `gate2.py`, `policy_engine.py`,
  `precedence.py` are pure evaluators with fixed BLOCK > REVIEW > REDACT >
  ALLOW precedence and fail-closed error handling. Seeded policies include
  `pol_block_secret_read` (Gate 2) and `pol_redact_secrets` (Gate 1).
- **Telemetry.** Every governed event flows through `telemetry/emitter.py`
  with a monotonic per-run `seq`. There is exactly one choke point.
- **Ports + adapters.** Eight ports; `LLMPort` returns a Bedrock-shaped
  `LLMResult`. `adapters/local/openai_compat_llm.py` speaks the OpenAI
  `/chat/completions` dialect for free cloud tiers (Groq & friends).
- **API.** FastAPI app in `main.py`, routers under `/api/v1`, WebSocket
  event stream, React/Vite console in `apps/web/`.
- **Tests.** `python tasks.py test` — 120 passing at baseline. The
  architecture guard (`tests/test_architecture.py`) enforces: adapters
  imported only by `container.py`; httpx/sqlite confined to
  `adapters/local`; only `config.py` reads `AGENTSHIELD_ENV`; only
  `container.py` branches on it.

## Simulated (retained for the office demo — not evidence of real execution)

- `sandbox/executor.py` + `sandbox/vfs.py`: every `run_tests`, `git_*`,
  `deploy`, `external_fetch` outcome is seeded simulation against an
  in-memory VFS. No process, no network, no filesystem.
- `adapters/local/mock_llm.py`: scripted model used as the default and as
  the honest degradation tier for the *simulation* (flagged `fallback=True`).

## Incomplete / known gaps

- `adapters/local/hybrid_llm.py` degrades cloud → local → mock for the
  simulation. That fail-open-to-script behaviour is correct for a game
  tick loop and **wrong** for a live coding run; Autopilot must not
  inherit it.
- The documented external Claude hook (`infra/scripts/claude_hook.py`)
  fails open on transport errors — noted in DEVIATIONS. Autopilot does
  not use it and is fail-closed instead.

## Implemented on `feat/nebius-autopilot`

1. `adapters/local/nebius_llm.py` — LLMPort against Nebius Token Factory
   (OpenAI-compatible) serving NVIDIA Nemotron. **No mock fallback**: a
   qualifying live run either uses the real model or fails loudly.
2. `agentshield/autopilot/` — schemas, workspace, explorer, patch engine,
   Docker-only test runner, bounded state machine, persisted report. Domain-level:
   depends on ports + governance, never on adapters.
3. `infra/fixtures/` — whitelisted disposable repos (`buggy-auth`,
   `prompt-injection`, `regression-guard`) with real failing tests.
4. `api/routes_autopilot.py` + one React page (`routes/autopilot.tsx`).
5. `infra/scripts/evaluate_autopilot.py` — measured, reproducible probes and
   live runs when prerequisites are available.

Live Nebius calls, Docker container runs, and the recorded submission demo
remain unverified because this machine has no Docker CLI and no Nebius key.

## Environment facts recorded at baseline (2026-10-26)

- `python tasks.py lint|typecheck|test` (API): all green, 120 passed.
- Web: 19 vitest tests pass; 3 pre-existing eslint errors in
  `routes/control/policies.tsx`, `policy-lab.tsx`, `routes/sandbox.tsx`
  (type-only imports) — fixed mechanically on this branch before new work.
- Docker CLI/daemon: **not installed** on this machine. Autopilot requires
  Docker and its prebuilt test image; coding jobs fail explicitly until both
  are available. There is no host-subprocess execution mode.
- `NEBIUS_API_KEY`: not configured in `.env` at baseline. Live Nemotron
  smoke tests require it; no mock substitution is permitted.
