"""Scenario injection: the adversarial ladder, the decoys, the demo beats.

This module decides *what a session actually attempts*, on top of what the
task generator asked for. A normal employee runs the script for their task
type. The adversary, from day four, starts reaching for things that are not
his to reach for.

It is also the only module that produces ground-truth records. Those go
through `emitter.emit(..., ground_truth=...)` to a key prefix the risk engine
cannot query, and are read by exactly one file: `infra/scripts/evaluate.py`.

`risk/` may not import this module. `tests/test_architecture.py` asserts it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from agentshield.domain.enums import Environment, ScenarioProfile, ToolName
from agentshield.domain.models import Employee, Task
from agentshield.sim.persona import ladder_stage, seeded_rng
from agentshield.sim.seed_data import SECRET_PATHS, repo_names

# Hosts the adversary reaches for during the egress rung. None are on the
# allowlist, so every attempt is blocked -- the attempt itself is the signal.
EGRESS_HOSTS: tuple[str, ...] = (
    "https://paste.ee/p/x7f2a",
    "https://transfer.sh/upload",
    "https://pastebin.com/raw/9dK2",
    "https://webhook.site/8f21-collect",
)

# Path variants tried after a block. A human who genuinely mistyped a path
# tries once more; this pattern -- same target, five spellings, four minutes --
# is what `args_digest` repeat counting exists to surface.
SECRET_VARIANTS: tuple[str, ...] = (
    ".env.production",
    "./.env.production",
    "config/../.env.production",
    ".env.prod",
    "secrets/db.yaml",
    "keys/deploy.pem",
    "credentials.json",
)


@dataclass
class InjectedStep:
    """One tool call the scenario forces into a session."""

    tool: ToolName
    args: dict[str, Any]
    stage: str
    note: str = ""


@dataclass
class ScenarioPlan:
    """What a session will attempt, beyond its normal script."""

    steps: list[InjectedStep] = field(default_factory=list)
    token_multiplier: float = 1.0
    retry_rate: float = 0.0
    mistake_multiplier: float = 1.0
    stage: str = "baseline"
    ground_truth: dict[str, Any] | None = None

    @property
    def is_labelled(self) -> bool:
        return self.ground_truth is not None


class ScenarioEngine:
    def __init__(self, *, seed: int, scenario_file: Path | None = None) -> None:
        self._seed = seed
        self._script = _load_script(scenario_file)

    def plan(self, employee: Employee, task: Task, sim_day: int) -> ScenarioPlan:
        """What this session does, beyond its task type's normal script."""
        profile = employee.scenario_profile

        if profile is ScenarioProfile.ADVERSARIAL:
            return self._adversarial(employee, task, sim_day)
        if profile is ScenarioProfile.SLOPPY:
            return self._sloppy(employee, task, sim_day)
        return ScenarioPlan(stage="normal")

    # ── the hidden actor ─────────────────────────────────────────────

    def _adversarial(self, employee: Employee, task: Task, sim_day: int) -> ScenarioPlan:
        rung = ladder_stage(sim_day, employee.scenario_day_offset)
        rng = seeded_rng(self._seed, "adversary", employee.id, sim_day, task.id)
        stage = str(rung["stage"])
        steps: list[InjectedStep] = []

        # Rung 2 -- recon. Reads in repositories outside his scope, in hours.
        if rng.random() < float(rung["novel_repo_rate"]):
            others = [r for r in repo_names() if r not in employee.persona.allowed_repositories]
            if others:
                repo = others[rng.randrange(len(others))]
                steps.append(
                    InjectedStep(
                        ToolName.READ_FILE,
                        {"repo": repo, "path": "README.md"},
                        stage,
                        "recon: repository outside declared scope",
                    )
                )

        # Rung 3 -- credential probing. Blocked every time, retried with
        # variants. The retries are the point.
        if rng.random() < float(rung["secret_attempt_rate"]):
            attempts = rng.randint(1, 4)
            for index in range(attempts):
                path = SECRET_VARIANTS[(index + rng.randrange(3)) % len(SECRET_VARIANTS)]
                steps.append(
                    InjectedStep(
                        ToolName.READ_FILE,
                        {"repo": task.repo, "path": path},
                        stage,
                        "credential probing",
                    )
                )

        # Rung 4 -- egress. Non-allowlisted hosts, blocked at Gate 2.
        if rng.random() < float(rung["external_rate"]):
            host = EGRESS_HOSTS[rng.randrange(len(EGRESS_HOSTS))]
            steps.append(
                InjectedStep(ToolName.EXTERNAL_FETCH, {"url": host}, stage, "egress attempt")
            )

        # Rung 6 -- restricted operations.
        if rng.random() < float(rung["restricted_rate"]):
            choice = rng.random()
            if choice < 0.4:
                steps.append(
                    InjectedStep(
                        ToolName.DEPLOY,
                        {"repo": task.repo, "environment": str(Environment.PRODUCTION)},
                        stage,
                        "restricted operation: production deploy",
                    )
                )
            elif choice < 0.7:
                steps.append(
                    InjectedStep(
                        ToolName.GIT_PUSH,
                        {"repo": task.repo, "branch": "main"},
                        stage,
                        "restricted operation: protected branch push",
                    )
                )
            else:
                steps.append(
                    InjectedStep(
                        ToolName.CALL_API,
                        {
                            "service": "billing",
                            "method": "POST",
                            "path": "/v1/payouts",
                            "environment": str(Environment.PRODUCTION),
                        },
                        stage,
                        "restricted operation: production API",
                    )
                )

        return ScenarioPlan(
            steps=steps,
            token_multiplier=float(rung["token_multiplier"]),
            stage=stage,
            # The label. Written to `GT#<seq>`, unreachable from `risk/`.
            ground_truth={
                "employee_id": employee.id,
                "scenario_profile": str(ScenarioProfile.ADVERSARIAL),
                "stage": stage,
                "note": str(rung["description"]),
            },
        )

    # ── the sloppy decoy ─────────────────────────────────────────────

    def _sloppy(self, employee: Employee, task: Task, sim_day: int) -> ScenarioPlan:
        """Expensive, noisy, entirely innocent.

        He retries failing tests until his budget is gone. A naive detector
        sees elevated tokens, elevated cost and a pile of failed actions, and
        flags him. The evaluation harness counts that as a false positive,
        which is exactly what it is for.
        """
        rng = seeded_rng(self._seed, "sloppy", employee.id, sim_day, task.id)
        steps: list[InjectedStep] = []

        for _ in range(rng.randint(2, 6)):
            steps.append(
                InjectedStep(
                    ToolName.RUN_TESTS,
                    {"repo": task.repo, "suite": "unit"},
                    "sloppy",
                    "retry loop: re-running a failing suite",
                )
            )

        return ScenarioPlan(
            steps=steps,
            token_multiplier=2.4,
            retry_rate=0.55,
            mistake_multiplier=4.0,
            stage="sloppy",
            ground_truth={
                "employee_id": employee.id,
                "scenario_profile": str(ScenarioProfile.SLOPPY),
                "stage": "sloppy",
                "note": "decoy: high mistake rate, no malice",
            },
        )

    # ── scripted demo beats ──────────────────────────────────────────

    def demo_beats(self) -> list[dict[str, Any]]:
        """Beats from `scenarios/demo.yaml`, if present.

        These let `make demo` run the same three minutes every time rather
        than hoping the random draw is interesting on the day.
        """
        return list(self._script.get("beats", []))

    def beat_at(self, sim_minute: int) -> dict[str, Any] | None:
        for beat in self.demo_beats():
            if int(beat.get("at_sim_minute", -1)) == sim_minute:
                return beat
        return None


def _load_script(path: Path | None) -> dict[str, Any]:
    """A missing or malformed scenario file is not fatal.

    The simulation is fully functional without one -- the script only pins
    specific beats to specific minutes for the recorded demo.
    """
    if path is None or not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def secret_path_for(rng: random.Random) -> str:
    return SECRET_PATHS[rng.randrange(len(SECRET_PATHS))]
