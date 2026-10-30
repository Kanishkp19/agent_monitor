# Nebius x NVIDIA Global AI Hackathon submission

Track: **Coding and Agentic Engineering Track**.

## Background and prior work

AgentShield began as a local-first governance and observability control plane
with a simulated office, policy engine, risk scoring, telemetry, and two runtime
gates. Those foundations and unrelated office artwork/provider changes are prior
work; we do not present the entire repository as newly built for this entry.

The `feat/nebius-autopilot` submission extends those foundations into a real
coding workflow. Work attributed to this submission window comprises:

- Dual-gate governance for the Autopilot coding loop: Gate 1 checks the prompt
  before model inference; Gate 2 evaluates proposed tools before execution.
  Patches also require the current source SHA-256, independently of policy.
- A disposable, non-root Docker pytest runner with no network, read-only fixture
  mounts, no Docker socket, dropped capabilities, and CPU/memory/PID/time limits.
- A sequenced telemetry event stream and cursor API with job state, model usage,
  gate decisions, patches, and test receipts; generated Python/TypeScript events.
- The `/autopilot` dashboard: fixture selection, credential setup guidance,
  before/after receipts, gate badges, latency/tokens, diff, and JSON report export.
- Three curated fixtures (`buggy-auth`, `prompt-injection`, `regression-guard`)
  and ten reproducible policy probes for permitted reads, traversal, and secrets.

This disclosure describes the branch's contribution, not a claim that every
uncommitted file was created during the eligible period. Before submitting,
attach the final commit range and verify development dates against the official
submission window; the current working tree alone cannot establish provenance.

## NVIDIA and Nebius integration

Autopilot always constructs `NebiusAdapter`, separately from simulator
`LLM_PROVIDER` routing. NVIDIA Nemotron via Nebius Token Factory reasons over
the goal and bounded repository/test context, proposes exact source patches,
and returns structured tool calls. The configured default is
`nvidia/nemotron-3-super-120b-a12b`, present in the
[official model catalog](https://tokenfactory.nebius.com/model-catalog.md)
when checked on 2026-10-26. The measured 2026-10-30 runs used the account's
configured `nvidia/nemotron-3.5-lightning-30b-a3b` instead; see
[live results](DEVPOST-READY.md).

The adapter sends OpenAI-compatible `messages` and `tools` with function names,
descriptions and JSON Schema parameters to `/chat/completions`. Tool arguments
are parsed and validated before execution; there is no custom textual tool-call
format. The system prompt treats repository contents as untrusted and requires
reads, hash-checked edits, and passing tests after an actual patch. AgentShield
governs model-proposed file accesses and test executions; a workspace boundary
also blocks secrets and escapes. Nemotron has no direct host shell access.

Token Factory supplies inference; Docker runs tests locally. We do not claim
Nebius AI Cloud deployment or NVIDIA GPU execution of local tests. Missing keys,
provider outages and blocked actions remain explicit errors, with no mock
substitution. Offline test doubles are engineering checks, not live evidence.

## Judge access and release

Follow the [README quickstart](../README.md#autopilot-judge-quickstart) and
[demo walkthrough](AUTOPILOT-DEMO.md). The root [MIT license](../LICENSE) covers
project-owned code. Existing third-party asset notices, including
`apps/web/public/assets/office/CREDITS.md` and font notices, retain their terms.

The [official rules](https://nebiusglobalaihackathon.devpost.com/rules) require
a public open-source repository, setup instructions, a working demo/test build,
a public YouTube demonstration, track selection, feedback, and prior-work
disclosure. This document prepares those materials; it does not publish them.

Remaining submission actions:

1. Record and upload a video under three minutes, then supply its public URL.
2. Supply the public repository and working demo/test-build URLs. Provide the
   demo token privately in judge testing instructions; never commit credentials.
3. Complete Token Factory/NVIDIA feedback based on the measured runs in
   [the Devpost draft](DEVPOST-READY.md).
