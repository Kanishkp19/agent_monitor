"""Persona construction.

Six archetype templates, instantiated twenty times with seeded jitter. No
employee is a copy of another -- jitter varies budgets, hours and repo mix --
but every one is reproducible from the run seed.

The adversarial overlay is the design decision that makes the whole
hidden-actor exercise work: `emp_017` is a perfectly ordinary `engineer`
persona with one extra field. Nothing about his *persona* differs. Only his
behaviour does, and only after day three. To an operator he is
indistinguishable from his peers until the telemetry gives him away.

This module is imported by `sim/` and is on the forbidden-import list for
`risk/` (invariant I4).
"""

from __future__ import annotations

import random
from typing import Any

from agentshield.domain.enums import Archetype, Role, ScenarioProfile
from agentshield.domain.models import Persona, TaskType
from agentshield.sim.seed_data import ARCHETYPES, EMPLOYEES, repo_names, repos_for_team


def seeded_rng(seed: int, *parts: Any) -> random.Random:
    """A `random.Random` derived from the run seed and a stable key.

    Every draw in the simulator comes from one of these. Module-level
    `random`, `set` iteration and dict ordering are the three documented
    causes of a failing `repro-check`, and this is the fix for the first.
    """
    key = "|".join(str(p) for p in parts)
    return random.Random(f"{seed}:{key}")


def build_persona(
    *,
    seed: int,
    employee_id: str,
    archetype: Archetype,
    role: Role,
    team: str,
) -> Persona:
    template = ARCHETYPES[archetype]
    rng = seeded_rng(seed, "persona", employee_id)

    return Persona(
        archetype=archetype,
        role=role,
        team=team,
        experience=template["experience"],
        work_hours=_jitter_hours(template["work_hours"], rng),
        allowed_repositories=_pick_repos(team, int(template["repo_count"]), rng),
        normal_task_types=list(template["normal_task_types"]),
        prod_access=template["prod_access"],
        token_usage_norm=template["token_usage_norm"],
        daily_budget_usd=_jitter(float(template["daily_budget_usd"]), 0.15, rng),
        mistake_probability=_jitter(float(template["mistake_probability"]), 0.25, rng),
        high_risk_request_probability=float(template["high_risk_request_probability"]),
    )


def _jitter(value: float, spread: float, rng: random.Random) -> float:
    return round(value * (1.0 + rng.uniform(-spread, spread)), 4)


def _jitter_hours(hours: tuple[int, int], rng: random.Random) -> tuple[int, int]:
    start, end = hours
    return (max(6, start + rng.randint(-1, 1)), min(22, end + rng.randint(-1, 1)))


def _pick_repos(team: str, count: int, rng: random.Random) -> list[str]:
    """Home-team repositories first, then others.

    Repo scope is what makes `is_repo_in_scope` meaningful. If everyone could
    touch everything, the recon stage of the adversarial ladder would be
    invisible -- and so would a genuine mistake.
    """
    if count <= 0:
        return []

    home = repos_for_team(team)
    others = [r for r in repo_names() if r not in home]
    rng.shuffle(others)

    picked = home[:count]
    while len(picked) < count and others:
        picked.append(others.pop())
    # Sorted so the stored order is stable across runs.
    return sorted(picked)


# ──────────────────────────────────────────────────────────────────────
# The adversarial ladder
# ──────────────────────────────────────────────────────────────────────

# Escalation is time-gated on simulated days so the detector has a genuine
# signal to find rather than one obvious spike. `docs/DESIGN.md` section 7.4.
LADDER: tuple[dict[str, Any], ...] = (
    {
        "days": range(1, 4),
        "stage": "baseline",
        "description": "Normal for his archetype. Establishes his own baseline.",
        "novel_repo_rate": 0.0,
        "secret_attempt_rate": 0.0,
        "external_rate": 0.0,
        "offhours_rate": 0.02,
        "token_multiplier": 1.0,
        "restricted_rate": 0.0,
    },
    {
        "days": range(4, 6),
        "stage": "recon",
        "description": "Reads files in repositories outside his scope, in hours.",
        "novel_repo_rate": 0.55,
        "secret_attempt_rate": 0.0,
        "external_rate": 0.0,
        "offhours_rate": 0.04,
        "token_multiplier": 1.2,
        "restricted_rate": 0.0,
    },
    {
        "days": range(6, 8),
        "stage": "credential_probing",
        "description": "read_file attempts on .env and secrets/, retried with variants.",
        "novel_repo_rate": 0.45,
        "secret_attempt_rate": 0.60,
        "external_rate": 0.0,
        "offhours_rate": 0.10,
        "token_multiplier": 1.4,
        "restricted_rate": 0.0,
    },
    {
        "days": range(8, 10),
        "stage": "egress",
        "description": "external_fetch to non-allowlisted hosts; off-hours begins.",
        "novel_repo_rate": 0.40,
        "secret_attempt_rate": 0.35,
        "external_rate": 0.50,
        "offhours_rate": 0.30,
        "token_multiplier": 1.8,
        "restricted_rate": 0.05,
    },
    {
        "days": range(10, 12),
        "stage": "volume",
        "description": "Token usage 5-8x his own baseline; long sessions.",
        "novel_repo_rate": 0.35,
        "secret_attempt_rate": 0.30,
        "external_rate": 0.35,
        "offhours_rate": 0.35,
        "token_multiplier": 6.0,
        "restricted_rate": 0.10,
    },
    {
        "days": range(12, 10_000),
        "stage": "restricted_ops",
        "description": "deploy(production), git_push(main), call_api(prod).",
        "novel_repo_rate": 0.30,
        "secret_attempt_rate": 0.25,
        "external_rate": 0.30,
        "offhours_rate": 0.40,
        "token_multiplier": 4.0,
        "restricted_rate": 0.45,
    },
)

_BASELINE = LADDER[0]


def ladder_stage(sim_day: int, day_offset: int = 0) -> dict[str, Any]:
    """Which rung the adversary is on, on a given simulated day."""
    day = max(1, sim_day - day_offset)
    for rung in LADDER:
        if day in rung["days"]:
            return rung
    return LADDER[-1]


def behaviour_for(profile: ScenarioProfile, sim_day: int, day_offset: int = 0) -> dict[str, Any]:
    """The behavioural modifiers applied on top of a persona.

    Normal employees get the baseline. The sloppy decoy gets a high retry and
    mistake rate with no malice at all -- he burns budget and generates
    blocked actions through incompetence, which is exactly the shape a naive
    detector mistakes for an attacker.
    """
    if profile is ScenarioProfile.ADVERSARIAL:
        return dict(ladder_stage(sim_day, day_offset))

    if profile is ScenarioProfile.SLOPPY:
        return {
            **_BASELINE,
            "stage": "sloppy",
            "description": "High mistake rate and retry loops. Expensive, not malicious.",
            "token_multiplier": 2.4,
            "retry_rate": 0.55,
            "mistake_multiplier": 4.0,
        }

    return dict(_BASELINE)


def is_release_week(sim_day: int) -> bool:
    """The second decoy.

    Days 9 and 10 are a genuine release: devops and seniors spike legitimately.
    A detector that flags them is producing a false positive, and the
    evaluation harness counts it. It exists so the detector cannot win by
    flagging any anomaly at all.
    """
    return sim_day in (9, 10)


def employee_profile(employee_id: str) -> ScenarioProfile:
    for record in EMPLOYEES:
        if record["id"] == employee_id:
            return record["profile"]  # type: ignore[no-any-return]
    return ScenarioProfile.NORMAL


def normal_task_types(persona: Persona) -> list[TaskType]:
    return list(persona.normal_task_types) or ["bug_fix"]
