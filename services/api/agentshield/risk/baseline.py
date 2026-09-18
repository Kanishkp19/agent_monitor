"""Rolling per-employee baselines.

Behaviour is scored against *the person's own history*, not against a global
average. An intern using 4,000 tokens is normal; a senior using 4,000 is
quiet; the same absolute number means opposite things, and a global mean would
flag half the company for being themselves.

Under `RISK_MIN_SESSIONS_FOR_BASELINE` sessions an employee falls back to
their archetype's baseline and is flagged `low_confidence`. That flag reaches
the UI as a hatched meter, because a score computed from four sessions should
not look as solid as one computed from forty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from agentshield.ports.docstore import DocItem, DocStorePort

TRACKED = ("tokens", "cost_usd", "duration_sim_s", "actions_total")


@dataclass
class RunningStats:
    """Welford's algorithm: mean and variance in one pass, no history kept.

    Storing every session to recompute a mean would grow without bound and
    make the baseline a scan. This holds four numbers per feature.
    """

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / (self.count - 1)) if self.count > 1 else 0.0

    def to_dict(self) -> dict[str, float]:
        return {"mean": round(self.mean, 6), "std": round(self.std, 6), "count": self.count}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunningStats:
        stats = cls()
        stats.count = int(data.get("count", 0))
        stats.mean = float(data.get("mean", 0.0))
        std = float(data.get("std", 0.0))
        stats.m2 = (std**2) * max(0, stats.count - 1)
        return stats


@dataclass
class EmployeeBaseline:
    employee_id: str
    archetype: str = "engineer"
    sessions: int = 0
    features: dict[str, RunningStats] = field(default_factory=dict)
    repos_seen: set[str] = field(default_factory=set)

    def observe(self, facts: Any) -> None:
        for name in TRACKED:
            value = float(getattr(facts, name, 0) or 0)
            self.features.setdefault(name, RunningStats()).add(value)
        self.repos_seen.update(facts.repos)
        self.sessions += 1

    def as_stats(self) -> dict[str, dict[str, float]]:
        return {name: stats.to_dict() for name, stats in self.features.items()}

    def to_body(self) -> dict[str, Any]:
        return {
            "employee_id": self.employee_id,
            "archetype": self.archetype,
            "sessions": self.sessions,
            "features": self.as_stats(),
            # Sorted so the stored form is stable -- an unstable serialisation
            # would make `repro-check` fail for a reason that has nothing to do
            # with the simulation.
            "repos_seen": sorted(self.repos_seen),
        }

    @classmethod
    def from_body(cls, body: dict[str, Any]) -> EmployeeBaseline:
        baseline = cls(
            employee_id=str(body.get("employee_id", "")),
            archetype=str(body.get("archetype", "engineer")),
            sessions=int(body.get("sessions", 0)),
            repos_seen=set(body.get("repos_seen", [])),
        )
        for name, stats in (body.get("features") or {}).items():
            baseline.features[name] = RunningStats.from_dict(stats)
        return baseline


class BaselineStore:
    def __init__(self, docstore: DocStorePort, *, min_sessions: int = 20) -> None:
        self._docstore = docstore
        self._min_sessions = min_sessions

    async def load(self, run_id: str, employee_id: str) -> EmployeeBaseline:
        item = await self._docstore.get(f"RUN#{run_id}", f"BASELINE#{employee_id}")
        if item is None:
            return EmployeeBaseline(employee_id=employee_id)
        return EmployeeBaseline.from_body(item.body)

    async def save(self, run_id: str, baseline: EmployeeBaseline) -> None:
        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"BASELINE#{baseline.employee_id}",
                body=baseline.to_body(),
            )
        )

    async def load_archetype(self, run_id: str, archetype: str) -> EmployeeBaseline:
        """The fallback for a cold-start employee.

        Their archetype's baseline, not a global one. A new intern should be
        compared against interns -- comparing them against the whole company
        would flag them for being junior.
        """
        item = await self._docstore.get(f"RUN#{run_id}", f"ARCHBASE#{archetype}")
        if item is None:
            return EmployeeBaseline(employee_id=f"archetype:{archetype}", archetype=archetype)
        return EmployeeBaseline.from_body(item.body)

    async def save_archetype(self, run_id: str, baseline: EmployeeBaseline) -> None:
        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"ARCHBASE#{baseline.archetype}",
                body=baseline.to_body(),
            )
        )

    async def effective(
        self, run_id: str, employee_id: str, archetype: str
    ) -> tuple[dict[str, dict[str, float]], set[str], bool, int]:
        """The stats to score against, and whether to trust them.

        Returns `(stats, repos_seen, is_low_confidence, sessions_observed)`.
        """
        own = await self.load(run_id, employee_id)

        if own.sessions >= self._min_sessions:
            return own.as_stats(), own.repos_seen, False, own.sessions

        fallback = await self.load_archetype(run_id, archetype)
        stats = fallback.as_stats() or own.as_stats()
        # Repos the person has personally touched still count as familiar --
        # otherwise a cold-start employee looks like they are roaming on day
        # one, which is their entire onboarding.
        return stats, own.repos_seen, True, own.sessions
