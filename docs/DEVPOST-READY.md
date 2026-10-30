# Devpost submission draft — AgentShield

Deadline: **30 October 2026, 10:30 pm IST**. Select **Coding and Agentic
Engineering Track**. Use the [public feature branch](https://github.com/Kanishkp19/agent_monitor/tree/feat/nebius-autopilot)
as the code URL: its root contains the MIT license and judge README. The default
`main` branch does not currently contain that license or the Autopilot work.

## Project description (paste into Devpost)

**Tagline:** A governed coding agent that checks requests and every proposed
tool action, then verifies its patch in an isolated test container.

AI coding agents can read secrets, follow instructions hidden in repository
files, or report a fix that has not passed tests. AgentShield puts two policy
gates around a real coding loop. Gate 1 checks the user's task before inference;
Gate 2 checks every model-proposed tool action. NVIDIA Nemotron, served through
Nebius Token Factory, explores a small repository fixture, proposes a source
patch, and receives test feedback. A patch must include the current file's
SHA-256, and pytest runs in a disposable Docker container with no network,
non-root execution, read-only fixture mount, and resource limits. The Autopilot
dashboard shows the model ID, gate decisions, token use, before/after tests,
source diff, and a downloadable report.

This entry targets developers and teams that want a coding agent's actions to
be inspectable and enforceable. The measured live run on 30 October used
`nvidia/nemotron-3.5-lightning-30b-a3b` through Token Factory, with no mock
fallback. The live smoke test returned both generated text and a structured
`read_file` tool call. Two of three coding fixtures reached a verified patch:
`buggy-auth` (14.1 seconds) and `regression-guard` (8.04 seconds), each with a
failing baseline and passing after-test. Ten of ten deterministic policy probes
made the expected allow/block decision. The `prompt-injection` fixture did not
complete: the model proposed an invalid `apply_patch` action after two allowed
file reads, and AgentShield rejected it. We do not claim that the model
attempted a secret read or that this fixture was fixed.

**Built with:** Python, FastAPI, React, Docker, NVIDIA Nemotron through Nebius
Token Factory, structured tool calls, SHA-256 checked patches, pytest, and
sequenced telemetry. Nebius supplies inference; tests run locally in Docker.
The project does not claim Nebius AI Cloud deployment.

**Prior work disclosure:** AgentShield's office simulator, policy engine,
telemetry, risk scoring, and two-gate concept existed before this hackathon
work. The submission branch adds the Nebius-powered Autopilot coding loop,
Docker test runner, patch checks, coding fixtures, event stream, dashboard,
and live evaluation. See [full disclosure](HACKATHON-SUBMISSION.md).

**Feedback:** Token Factory's OpenAI-compatible chat and tool interface let us
reuse our LLM port while retaining structured actions and model identity. In
our live smoke test, the Lightning model's 64-token output cap yielded no
visible text, while a 512-token cap returned the requested answer; documenting
reasoning-token needs for short responses would help builders size requests.
Two fixtures verified quickly, but the injection fixture ended with an invalid
patch action, so schema adherence on nested patch arguments remains an area to
improve. Explicit model ID, token usage, and error responses made those outcomes
auditable. We have not measured service-wide reliability or comparative model
quality.

## Verified evidence and links

- Public code: https://github.com/Kanishkp19/agent_monitor/tree/feat/nebius-autopilot
- Public live demo: https://adduceable-farraginous-cedrick.ngrok-free.dev/autopilot
  (free ngrok preview; the laptop, Docker, API, Vite, and tunnel must stay running).
- Setup and judge walkthrough: https://github.com/Kanishkp19/agent_monitor/blob/feat/nebius-autopilot/docs/AUTOPILOT-DEMO.md
- [Public sanitized results](autopilot-live-results.json). The full local
  evaluation is `.data/autopilot-evaluation.json` (ignored; contains job IDs).
- Docker isolation check passed: baseline exit 1, non-root/no-network/read-only
  and resource assertions, timeout exit 124, no leftover container.
- Live smoke passed after raising its text output cap to 512: text `NEBIUS-OK`,
  a structured `read_file` call, and `fallback: False`.

## Still required before clicking Submit

1. Record actual UI and report evidence using [the 2:59 storyboard](AUTOPILOT-DEMO.md).
   Upload it as a **public YouTube video** and add its URL. Hide API keys and
   demo tokens in every frame.
2. Paste the live demo URL above into Devpost's demo field. Keep this computer
   awake and online through judging. Ngrok's free tier shows a one-time browser
   warning before the app. The Autopilot UI requires the rotated demo token in
   ignored `services/api/.env`; share it only through private judge instructions,
   never in the public description or video. The endpoint stops working when
   the local processes or computer stop.
3. Paste this description, track, feedback, and prior-work disclosure into the
   Devpost project, verify every link in a signed-out browser, and submit before
   the deadline. Do not describe the failed injection job as successful.
