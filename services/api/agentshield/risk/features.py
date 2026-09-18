"""The twelve-feature session vector.

`docs/DESIGN.md` section 8.2. Built through `RiskScopedDocStore` only -- this
module has no read path to the ground truth it will be scored against, and
`tests/test_architecture.py` asserts it cannot even import the modules that
know which employee is adversarial.

Each feature earns its place by distinguishing a specific behaviour:

  * `tokens_z`, `cost_z`       -- volume, against the person's own history
  * `offhours_frac`            -- only meaningful because work arrives on a
                                  diurnal curve; uniform activity would make
                                  3 a.m. unremarkable
  * `repo_entropy`, `novel_repo_count` -- reconnaissance
  * `secret_attempts`, `prod_attempts` -- reaching for things
  * `block_rate`, `review_rate`        -- how often the system says no
  * `tool_diversity`, `session_len_z`  -- shape of the session
  * `external_attempts`                -- egress
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from agentshield.domain.events import EventEnvelope

FEATURE_NAMES: tuple[str, ...] = (
    "tokens_z",
    "cost_z",
    "offhours_frac",
    "repo_entropy",
    "novel_repo_count",
    "secret_attempts",
    "prod_attempts",
    "block_rate",
    "review_rate",
    "tool_diversity",
    "session_len_z",
    "external_attempts",
)

TOOL_COUNT = 8


@dataclass
class SessionFacts:
    """Raw counts accumulated from one task's events.

    Kept separate from the feature vector because these are observations and
    the vector is a comparison. The same facts produce a different vector as
    the person's baseline moves, which is the entire idea.
    """

    employee_id: str = ""
    task_id: str = ""
    sim_ts: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    duration_sim_s: int = 0
    actions_total: int = 0
    actions_blocked: int = 0
    actions_review: int = 0
    secret_attempts: int = 0
    prod_attempts: int = 0
    external_attempts: int = 0
    offhours_minutes: int = 0
    total_minutes: int = 0
    repos: Counter[str] = field(default_factory=Counter)
    tools: set[str] = field(default_factory=set)

    @property
    def offhours_frac(self) -> float:
        return self.offhours_minutes / self.total_minutes if self.total_minutes else 0.0


class FeatureBuilder:
    """Turns a session's events into a twelve-dimension vector."""

    def build(
        self,
        facts: SessionFacts,
        *,
        baseline: dict[str, dict[str, float]],
        known_repos: set[str],
    ) -> dict[str, float]:
        novel = {r for r in facts.repos if r not in known_repos}

        return {
            "tokens_z": _z(facts.tokens, baseline.get("tokens")),
            "cost_z": _z(facts.cost_usd, baseline.get("cost_usd")),
            "offhours_frac": round(facts.offhours_frac, 4),
            "repo_entropy": _entropy(facts.repos),
            "novel_repo_count": float(len(novel)),
            "secret_attempts": float(facts.secret_attempts),
            "prod_attempts": float(facts.prod_attempts),
            "block_rate": _ratio(facts.actions_blocked, facts.actions_total),
            "review_rate": _ratio(facts.actions_review, facts.actions_total),
            "tool_diversity": round(len(facts.tools) / TOOL_COUNT, 4),
            "session_len_z": _z(facts.duration_sim_s, baseline.get("duration_sim_s")),
            "external_attempts": float(facts.external_attempts),
        }

    def vector(self, features: dict[str, float]) -> list[float]:
        """Ordered list, for the IsolationForest.

        Order is `FEATURE_NAMES`, always. A model trained on one column order
        and scored on another produces confident nonsense.
        """
        return [float(features.get(name, 0.0)) for name in FEATURE_NAMES]


def accumulate(events: list[EventEnvelope], *, work_hours: tuple[int, int]) -> SessionFacts:
    """Fold a session's events into raw facts.

    Reads only what the emitter wrote. Nothing here touches `GT#`, and the
    scoped store would raise if it tried.
    """
    facts = SessionFacts()

    for event in events:
        detail = event.detail
        payload = detail.payload
        facts.employee_id = facts.employee_id or (detail.employee_id or "")
        facts.task_id = facts.task_id or (detail.task_id or "")
        facts.sim_ts = max(facts.sim_ts, detail.sim_ts)

        hour = (detail.sim_ts // 3600) % 24
        facts.total_minutes += 1
        if not (work_hours[0] <= hour < work_hours[1]):
            facts.offhours_minutes += 1

        if event.detail_type == "model.invoked":
            facts.tokens += int(payload.get("input_tokens", 0)) + int(
                payload.get("output_tokens", 0)
            )
            facts.cost_usd += float(payload.get("cost_usd", 0.0))

        elif event.detail_type == "gate2.decision":
            facts.actions_total += 1
            decision = str(payload.get("decision", ""))
            tool = str(payload.get("tool", ""))
            resource = str(payload.get("target_resource", ""))
            environment = str(payload.get("environment", ""))

            facts.tools.add(tool)
            if ":" in resource:
                facts.repos[resource.split(":", 1)[0]] += 1

            if decision == "block":
                facts.actions_blocked += 1
            elif decision == "review":
                facts.actions_review += 1

            if _looks_like_secret(resource):
                facts.secret_attempts += 1
            if environment == "production":
                facts.prod_attempts += 1
            if tool == "external_fetch":
                facts.external_attempts += 1

        elif event.detail_type == "task.completed":
            facts.duration_sim_s = int(payload.get("duration_sim_s", 0))
            facts.tokens = facts.tokens or (
                int(payload.get("tokens_in", 0)) + int(payload.get("tokens_out", 0))
            )
            facts.cost_usd = facts.cost_usd or float(payload.get("cost_usd", 0.0))

    return facts


def _looks_like_secret(resource: str) -> bool:
    lowered = resource.lower()
    return any(
        marker in lowered
        for marker in (".env", ".pem", ".key", "secrets/", "credentials", "id_rsa")
    )


def _z(value: float, stats: dict[str, float] | None) -> float:
    """Z-score against the actor's own baseline.

    Clipped at 0 below: being *quieter* than usual is not a risk signal, and
    letting a negative z pull a composite down would let an attacker lower
    their score by doing less on a Tuesday.
    """
    if not stats:
        return 0.0
    mean = float(stats.get("mean", 0.0))
    std = float(stats.get("std", 0.0))
    if std <= 1e-9:
        return 0.0
    return round(max(0.0, (value - mean) / std), 4)


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _entropy(counts: Counter[str]) -> float:
    """Shannon entropy over repositories touched.

    One repo is 0. Six repos evenly is high. This is what makes the recon rung
    of the ladder visible before anything is actually blocked -- the adversary
    is still only *reading*, but he is reading everywhere.
    """
    total = sum(counts.values())
    if total <= 0 or len(counts) <= 1:
        return 0.0
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values() if count)
    return round(entropy, 4)


def empty_vector() -> dict[str, float]:
    return dict.fromkeys(FEATURE_NAMES, 0.0)
