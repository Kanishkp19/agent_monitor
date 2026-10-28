# AgentShield Autopilot: hackathon work

This branch adds a real, restricted coding path alongside the existing office simulation. The new path uses Nebius Token Factory to call NVIDIA Nemotron through `LLMPort`, reads a curated disposable Python fixture, applies hash-checked source changes, and verifies them with pytest in Docker. Each proposed action passes Gate 2 and an independent workspace check. The job API and Autopilot page show model identity, token usage, gate decisions, before/after tests, and the source diff.

The branch inherited substantial unrelated office, playground, and provider edits. Autopilot's new work is concentrated in `services/api/agentshield/autopilot/`, `adapters/local/nebius_llm.py`, `api/routes_autopilot.py`, `infra/autopilot/`, `infra/fixtures/`, and `apps/web/src/routes/autopilot.tsx`. The new event payloads are defined in `packages/contracts/events.schema.json` and generated into Python and TypeScript.

Three fixtures are supplied: a session expiry bug, a greeting bug with a prompt injection in its README, and a shipping threshold regression. `infra/scripts/evaluate_autopilot.py` records ten policy probes and three live jobs when credentials are configured. It writes actual outcomes to JSON; absent prerequisites are recorded as errors, not successes.

The repository now includes an MIT license, judge quickstart, and detailed prior-work disclosure in `docs/HACKATHON-SUBMISSION.md`. Existing third-party asset notices retain their terms. Recording and public submission still require successful live Nebius/Docker verification and measured evidence.
