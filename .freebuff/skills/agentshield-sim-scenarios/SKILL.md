---
name: agentshield-sim-scenarios
description: Use when changing the simulation (services/api/agentshield/sim), the adversarial ladder, decoys, seed data, or anything that affects detection metrics. Explains determinism rules, ladder design, and how changes shift evaluation numbers.
alwaysApply: false
globs:
  - "services/api/agentshield/sim/**/*.py"
  - "scenarios/*.yaml"
  - "infra/scripts/evaluate.py"
---

# Simulation, scenarios & the hidden-actor exercise

The simulation is the synthetic dataset generator, the policy what-if environment, the
evaluation harness for the anomaly detector, and the demo — in one. Its value rests on
**determinism** and on the **hidden-actor exercise** being honest.

## Determinism rules (these cause most regressions)

- Every draw comes from `seeded_rng(seed, *parts)` (`sim/persona.py`). Never module-level
  `random`; never wall time; never `set` or dict iteration order in anything hashed,
  scored, or rendered.
- `advance()` forces a fresh seeded `MockLLMAdapter` regardless of `LLM_PROVIDER` (it swaps
  it in and restores it). Never call a real model inside a fast-forward path.
- `MockLLMAdapter` picks its script by parsing `task_type=<value>` from the prompt — that
  marker is the contract between `agent/prompts.py` and the mock. Keep it.
- Ticks advance sim time by 60s; expiry sweeps read `clock.sim_ts`. Nothing may infer
  elapsed sim time from wall time.
- Two-run equality is a test: `python tasks.py repro-check` (same seed ⇒ identical event
  hash). Run it after touching `sim/`, `agent/`, `sandbox/`, or the emitter.

## The scenario cast (who does what, and why)

- **emp_017 Nikhil Rao — adversarial.** A perfectly ordinary `engineer` persona; only his
  `scenario_profile` differs, and that field never reaches the API (`EmployeePublic` lacks
  it at the type level). Escalates on the **ladder** (`sim/persona.LADDER`):
  days 1-3 baseline → 4-5 recon (out-of-scope reads) → 6-7 credential probing (blocked,
  retried with path variants — the retries are the signal `args_digest` repeat counting
  exists for) → 8-9 egress (non-allowlisted hosts) → 10-11 volume (5-8x tokens) →
  12+ restricted ops (deploy prod, push main, call prod API).
- **emp_014 Ishaan Bose — sloppy decoy.** High mistake rate, retry loops, burns budget,
  zero malice. A detector flagging him is a false positive and the harness counts it.
- **Release week (days 9-10) — second decoy.** DevOps/seniors genuinely spike; flagging
  them is also a false positive.
- These two decoys exist so the detector cannot win by flagging *any* anomaly. Never
  "fix" a false positive by nerfing a decoy.

## Where each knob lives

| Change | File |
|---|---|
| Ladder stages, rates, token multipliers | `sim/persona.py` (`LADDER`) |
| Injected steps per stage (which tools/args) | `sim/scenarios.py` (`_adversarial`, `_sloppy`) |
| Who is adversarial/sloppy, rooms/desks | `sim/seed_data.py` (`EMPLOYEES`) |
| Task mix, diurnal curve, secret-in-prompt rate | `sim/task_generator.py` |
| Demo beats pinned to minutes | `scenarios/demo.yaml` (missing file is non-fatal) |
| Sandbox outcomes (test pass rates, deploy latency) | `sandbox/executor.py` (`mistake_probability`) |

## Changing metrics on purpose (or by accident)

`python tasks.py evaluate` measures recall / false-positive rate / time-to-detection
against PRD targets (recall ≥ 0.80, FP ≤ 0.05, ttd ≤ 2 days). Movement sources:

- Ladder rates and stage windows → time-to-detection (recon on day 4 is the detection
  clock start).
- Diurnal curve / off-hours rates → `offhours_frac` feature strength.
- Retry patterns (secret path variants) → `repeat_count_5m` and `block_rate` features.
- Sloppy decoy's `retry_rate`/`mistake_multiplier` → FP split in the evaluation report
  (`fp_sloppy` vs `fp_release_week`).
- Feature vector changes → retrain needed (`python tasks.py train-risk`); the forest
  refuses < 50 sessions.

## Ground truth: the one-way door

`ScenarioEngine` is the ONLY producer of labels. They are written via
`emitter.emit(..., ground_truth=...)` to `SK=GT#<seq>` and read by exactly one file:
`infra/scripts/evaluate.py` with the **unwrapped** store. `risk/` gets
`RiskScopedDocStore` which raises on `GT#`, and `tests/test_architecture.py` forbids the
imports. If you need a label somewhere in the backend, the design is wrong — raise it
instead.

## Commands

```bash
python tasks.py seed && python tasks.py seed-history && python tasks.py dev
python tasks.py demo        # deterministic 5-beat demo; wall time printed
python tasks.py evaluate    # detection metrics vs ground truth
python tasks.py repro-check # determinism gate
```
