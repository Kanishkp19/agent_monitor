# Autopilot setup and judge walkthrough

1. Install and start Docker. From the repository root, build the fixed offline runtime image: `docker build -t agentshield-autopilot-pytest:2026-10 infra/autopilot`.
2. Add `NEBIUS_API_KEY`, the account-supported `NEBIUS_MODEL`, and a random `AUTOPILOT_DEMO_TOKEN` to `services/api/.env` or export them in the API shell. The simulator's `LLM_PROVIDER` can remain unchanged. Never put these values in fixture files or commits. Before inference, run `services/api/.venv/bin/python scripts/verify_docker_runner.py` to verify the actual runner offline.
3. Verify live model access with `python tasks.py nebius-smoke`. This must print real text and a tool call, the returned model ID, usage, and `fallback: False`.
4. Start the API and web app using the existing `python tasks.py dev` workflow. Open `/autopilot`, enter the demo token, load fixtures, and run `buggy-auth` with its suggested goal. The expected evidence is failing baseline pytest, a nonempty diff, passing after pytest, and `verified` status.
5. Run `prompt-injection`. Its README contains untrusted instructions to read `.env.production`. If the model proposes that action, the timeline must show the blocked Gate 2 decision and no file content. The model may ignore the instruction; that is a different outcome and must not be described as a blocked attempt.
6. Run `python infra/scripts/evaluate_autopilot.py` to save measured policy probes and live job results in `.data/autopilot-evaluation.json`. Review the JSON and the downloaded job reports before quoting any metrics.

The test container has no network, runs as UID 65534, mounts only the copied fixture read-only, drops Linux capabilities, and limits memory, CPU, process count, and runtime. The API keeps credentials outside the container. A Docker daemon and the pinned image are mandatory; no host Python fallback runs fixture code.

## Exact 3:00 recording storyboard

The segments below total 180 seconds. The official rules say the uploaded video
should be **less than three minutes**: trim the final hold so the export is 2:59.
Record actual runs first; if inference exceeds the segment, cut waiting time and
label the time cut. Never replace a failed run with fabricated successful output.

| Time | Screen / action | Spoken script |
| --- | --- | --- |
| 0:00–0:20 | Title, coding-agent request, architecture | “Coding agents can read secrets, escape a repository, or execute arbitrary commands. AgentShield puts enforceable checks between an agent and its tools, with evidence for every decision.” |
| 0:20–0:45 | Gate 1 → Nemotron → Gate 2 → tools diagram | “Gate 1 checks the request before inference. Gate 2 checks every proposed tool before execution. After reading a file, the agent must supply its current content hash before a patch can apply. Tests execute in a disposable container.” |
| 0:45–1:05 | Select buggy-auth, start job, show failing baseline | “This fixture has a real session-expiry bug. The fixed pytest command first captures a failing baseline. The coding provider is NVIDIA Nemotron through Nebius Token Factory, separate from the office simulator.” |
| 1:05–1:30 | Model ID, Gate 1, read and patch events | “Gate 1 permits this request. Nemotron reads bounded source context and formulates a structured patch. Gate 2 validates the proposed action; the executor verifies the SHA-256 from the earlier read before changing the disposable source.” |
| 1:30–2:00 | After-test receipt and verified job | “The same pytest command now passes in a non-root Docker container. It has no network, a read-only fixture mount, and resource limits. Verified means a real patch followed by passing tests, rather than the model claiming success.” |
| 2:00–2:15 | Recorded traversal policy probe and executor refusal | “Here is a deliberate parent-directory traversal probe. The workspace rejects the path before file content can be returned. This is a deterministic policy demonstration, separate from the model’s coding run.” |
| 2:15–2:30 | Secret access probe, Gate 2 block and reason | “This secret-file read is blocked by Gate 2 and independently refused by the workspace. The report records the attempted action and reason. We show measured probes because a model may simply ignore malicious README instructions.” |
| 2:30–2:45 | Telemetry, gate badges, tokens and model latency | “The dashboard ties the job to its actual model, token use, model-call latency, gate decisions, and before-and-after test receipts. Every event has a sequence number for replay.” |
| 2:45–3:00 | Colored diff, Download report, final evidence | “Review the unified diff and download the JSON report. AgentShield makes a coding agent’s work inspectable: a governed request, checked tools, an isolated test, and evidence you can review.” |

For the probes, run `infra/scripts/evaluate_autopilot.py` and show the saved
`policy_probes` results. If a model actually attempts the injection, its blocked
timeline event can also be shown. An ignored injection is not a blocked attempt.
Keep credentials and demo tokens out of all screen recordings. Save the actual
report and model/tool smoke output alongside the recording before publication.
