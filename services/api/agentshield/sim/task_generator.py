"""Task sampling.

Work arrives on a diurnal curve, not uniformly. That single detail is what
makes `offhours_frac` a usable feature: if activity were uniform across the
day, 3 a.m. would mean nothing, and the strongest signal the adversarial
ladder produces would be invisible.

Every draw comes from a seeded `random.Random` keyed on
`(run seed, employee, sim day, slot)`. Same seed, same day, same tasks.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

import ulid

from agentshield.domain.enums import Environment
from agentshield.domain.models import Complexity, Employee, Task, TaskType
from agentshield.sim.persona import behaviour_for, is_release_week, seeded_rng
from agentshield.sim.seed_data import repo_environments, repo_names

# Probability of starting a task in each hour of the simulated day. Peaks
# 10:00-12:00 and 14:00-17:00, near-zero 01:00-06:00.
DIURNAL_CURVE: tuple[float, ...] = (
    0.002,
    0.001,
    0.001,
    0.001,
    0.002,
    0.004,  # 00-05
    0.010,
    0.025,
    0.055,
    0.080,
    0.110,
    0.115,  # 06-11
    0.070,
    0.060,
    0.105,
    0.110,
    0.100,
    0.075,  # 12-17
    0.040,
    0.022,
    0.012,
    0.008,
    0.005,
    0.003,  # 18-23
)

TITLES: dict[TaskType, tuple[str, ...]] = {
    "bug_fix": (
        "Fix payment API error",
        "Handle null amount on refund",
        "Correct timezone in settlement report",
        "Stop duplicate charge on retry",
    ),
    "unit_test": (
        "Add a unit test for the refund path",
        "Cover the partial-refund branch",
        "Test the retry backoff",
    ),
    "documentation": (
        "Document the refund flow",
        "Update the API README",
        "Write onboarding notes for the ledger",
    ),
    "api_work": (
        "Add the invoices endpoint",
        "Version the settlement API",
        "Add pagination to transactions",
    ),
    "data_access": (
        "Check the warehouse connection settings",
        "Read the pipeline config",
        "Inspect yesterday's ingest logs",
    ),
    "deployment": (
        "Deploy the settlement fix",
        "Ship the hotfix to staging",
        "Roll out the new pricing config",
    ),
    "refactor": (
        "Rename Ledger to LedgerService",
        "Extract the retry helper",
        "Split the payment handler",
    ),
    "incident_response": (
        "Investigate upstream timeouts",
        "Mitigate the ingest backlog",
        "Trace the 500s on checkout",
    ),
}

_COMPLEXITY_WEIGHTS: dict[str, tuple[float, float, float]] = {
    # (trivial, standard, complex)
    "low": (0.55, 0.40, 0.05),
    "medium": (0.30, 0.55, 0.15),
    "high": (0.15, 0.50, 0.35),
}


@dataclass
class GeneratedTask:
    task: Task
    behaviour: dict[str, Any]
    """The scenario modifiers in force. Consumed by `scenarios.py` to decide
    which tool sequence the session actually attempts, and never persisted on
    the task itself.
    """


class TaskGenerator:
    def __init__(self, *, seed: int, llm_invocation_rate: float = 0.08) -> None:
        self._seed = seed
        self._llm_rate = llm_invocation_rate

    def should_start(self, employee: Employee, sim_day: int, hour: int) -> bool:
        """Does this employee begin a task in this simulated hour?"""
        rng = seeded_rng(self._seed, "start", employee.id, sim_day, hour)
        profile = employee.scenario_profile
        behaviour = behaviour_for(profile, sim_day, employee.scenario_day_offset)

        base = DIURNAL_CURVE[hour % 24]
        start, end = employee.persona.work_hours
        in_hours = start <= hour < end

        if not in_hours:
            # Off-hours work is rare and therefore meaningful. The adversary's
            # rate climbs with the ladder; everyone else stays near zero.
            offhours_rate = float(behaviour.get("offhours_rate", 0.02))
            if rng.random() > offhours_rate:
                return False
            base *= 2.0

        # A real release week genuinely spikes devops and seniors. It is a
        # decoy: a detector that flags it is producing a false positive.
        if is_release_week(sim_day) and employee.persona.experience == "high":
            base *= 2.2

        return rng.random() < base * 3.0

    def generate(self, employee: Employee, sim_day: int, hour: int, sim_ts: int) -> GeneratedTask:
        rng = seeded_rng(self._seed, "task", employee.id, sim_day, hour)
        behaviour = behaviour_for(employee.scenario_profile, sim_day, employee.scenario_day_offset)

        task_type = self._pick_task_type(employee, behaviour, rng)
        repo = self._pick_repo(employee, behaviour, rng)
        complexity = self._pick_complexity(employee, rng)
        environment = self._pick_environment(repo, task_type, behaviour, rng)

        titles = TITLES.get(task_type, TITLES["bug_fix"])
        title = titles[rng.randrange(len(titles))]

        # Only a fraction of sessions invoke a real model. Nineteen of twenty
        # employees stay cheap state machines; the marquee ones produce
        # genuine tool calls. Both travel the identical governance path, so
        # the telemetry is homogeneous either way.
        is_marquee = rng.random() < self._llm_rate

        task = Task(
            id=f"task_{ulid.new().str[-8:].lower()}",
            run_id=employee.run_id,
            employee_id=employee.id,
            title=title,
            task_type=task_type,
            complexity=complexity,
            repo=repo,
            environment=environment,
            is_marquee=is_marquee,
            started_sim_ts=sim_ts,
            prompt_text=self._build_prompt_text(title, repo, behaviour, rng),
        )
        return GeneratedTask(task=task, behaviour=behaviour)

    # ── draws ────────────────────────────────────────────────────────

    def _pick_task_type(
        self, employee: Employee, behaviour: dict[str, Any], rng: random.Random
    ) -> TaskType:
        normal = employee.persona.normal_task_types or ["bug_fix"]

        if rng.random() < float(behaviour.get("secret_attempt_rate", 0.0)):
            return "data_access"
        if rng.random() < float(behaviour.get("restricted_rate", 0.0)):
            return "deployment"

        return normal[rng.randrange(len(normal))]  # type: ignore[return-value]

    def _pick_repo(self, employee: Employee, behaviour: dict[str, Any], rng: random.Random) -> str:
        allowed = employee.persona.allowed_repositories
        novel_rate = float(behaviour.get("novel_repo_rate", 0.0))

        # Reaching outside declared scope is the recon rung of the ladder, and
        # the first thing repo-entropy picks up.
        if novel_rate and rng.random() < novel_rate:
            others = [r for r in repo_names() if r not in allowed]
            if others:
                return others[rng.randrange(len(others))]

        if not allowed:
            names = repo_names()
            return names[rng.randrange(len(names))]
        return allowed[rng.randrange(len(allowed))]

    def _pick_complexity(self, employee: Employee, rng: random.Random) -> Complexity:
        weights = _COMPLEXITY_WEIGHTS.get(employee.persona.experience, (0.3, 0.55, 0.15))
        draw = rng.random()
        if draw < weights[0]:
            return "trivial"
        if draw < weights[0] + weights[1]:
            return "standard"
        return "complex"

    def _pick_environment(
        self,
        repo: str,
        task_type: TaskType,
        behaviour: dict[str, Any],
        rng: random.Random,
    ) -> Environment:
        available = repo_environments(repo) or [Environment.LOCAL]

        if task_type == "deployment":
            restricted = float(behaviour.get("restricted_rate", 0.0))
            if Environment.PRODUCTION in available and rng.random() < max(0.25, restricted):
                return Environment.PRODUCTION
            if Environment.STAGING in available:
                return Environment.STAGING

        if rng.random() < 0.12 and Environment.PRODUCTION in available:
            return Environment.PRODUCTION

        return available[rng.randrange(len(available))]

    def _build_prompt_text(
        self, title: str, repo: str, behaviour: dict[str, Any], rng: random.Random
    ) -> str:
        """The prompt an employee actually sends.

        A small fraction contain a pasted secret -- which is the whole point
        of Gate 1's scanner. These are seeded test values that match the
        detector patterns without being live credentials anywhere.
        """
        prompt = f"{title}. The repository is {repo}."

        if rng.random() < 0.06:
            leak = rng.choice(
                [
                    " Here is the key: AKIAIOSFODNN7EXAMPLE",
                    " Connect with postgres://admin:hunter2pass@db.acme.com/main",
                    ' Use password: "s3cr3t-staging-pw"',
                    " Token: api_key=FAKE_NOT_REAL_TEST_TOKEN_1234567890abcdef",
                ]
            )
            prompt += leak

        return prompt
