"""The risk engine: observe, score, persist, open incidents.

Wires the four pieces together. It receives every event through the emitter's
fan-out, accumulates per-session facts, and scores a session when it
completes.

The store it holds is a `RiskScopedDocStore`. It cannot read `GT#` -- the
wrapper raises -- and it cannot import the modules that know which employee is
adversarial, because `tests/test_architecture.py` forbids it. Both halves are
needed: the static check stops the import, the runtime check stops a
dynamically constructed key.
"""

from __future__ import annotations

import logging
from typing import Any

from agentshield.domain.enums import Role, Sensitivity
from agentshield.domain.events import EventEnvelope
from agentshield.domain.models import RiskProfile
from agentshield.ports.docstore import DocItem
from agentshield.risk import scoring
from agentshield.risk.baseline import BaselineStore
from agentshield.risk.features import FeatureBuilder, SessionFacts, accumulate, empty_vector
from agentshield.risk.incidents import IncidentManager, evidence_from_event
from agentshield.risk.isolation import AnomalyDetector
from agentshield.risk.scoped_store import RiskScopedDocStore

logger = logging.getLogger(__name__)


class RiskEngine:
    def __init__(
        self,
        *,
        store: RiskScopedDocStore,
        baselines: BaselineStore,
        detector: AnomalyDetector,
        incidents: IncidentManager,
        min_sessions: int = 20,
    ) -> None:
        self._store = store
        self._baselines = baselines
        self._detector = detector
        self._incidents = incidents
        self._features = FeatureBuilder()
        self._min_sessions = min_sessions

        # Open sessions, keyed by task id. Held in memory because a session
        # lives for minutes and writing a partial vector on every event would
        # be forty writes per task for no gain.
        self._open: dict[str, list[EventEnvelope]] = {}
        self._actors: dict[str, dict[str, Any]] = {}

    # ── the emitter's fan-out lands here ─────────────────────────────

    async def observe(self, envelope: EventEnvelope) -> None:
        """Incremental accumulation. Must never raise into the emitter.

        A failure here would be a scoring gap, not a governance failure, and
        the emitter treats it that way -- but keeping it quiet on our side
        means a broken detector cannot slow the gates down either.
        """
        task_id = envelope.detail.task_id
        if not task_id:
            return

        self._open.setdefault(task_id, []).append(envelope)

        if envelope.detail_type == "task.completed":
            events = self._open.pop(task_id, [])
            try:
                await self.score_session(envelope.detail.run_id, events)
            except Exception:
                logger.exception("session scoring failed", extra={"task_id": task_id})

    # ── scoring one session ──────────────────────────────────────────

    async def score_session(self, run_id: str, events: list[EventEnvelope]) -> RiskProfile | None:
        if not events:
            return None

        employee_id = next((e.detail.employee_id for e in events if e.detail.employee_id), None)
        if not employee_id:
            return None

        actor = await self._actor(run_id, employee_id)
        work_hours = tuple(actor.get("work_hours", (9, 18)))

        facts = accumulate(events, work_hours=work_hours)
        facts.employee_id = employee_id

        stats, known_repos, low_confidence, sessions = await self._baselines.effective(
            run_id, employee_id, str(actor.get("archetype", "engineer"))
        )

        features = self._features.build(facts, baseline=stats, known_repos=known_repos)
        vector = self._features.vector(features)

        static = self._static_for(facts, actor)
        behavioural = scoring.behavioural_score(features)
        ml = self._detector.score(vector) if self._detector.is_trained else 0

        composite = scoring.composite(
            static=static,
            behavioural=behavioural,
            ml=ml,
            features=features,
            baseline=stats,
            is_low_confidence=low_confidence or sessions < self._min_sessions,
        )

        profile = RiskProfile(
            employee_id=employee_id,
            run_id=run_id,
            score=composite.score,
            static=composite.static,
            behavioural=composite.behavioural,
            ml=composite.ml,
            confidence=composite.confidence,
            top_factors=composite.top_factors,
            features=features,
            sessions_observed=sessions,
            updated_sim_ts=facts.sim_ts,
        )
        await self._persist(run_id, profile)

        # The baseline learns from this session *after* it was scored against
        # the previous one. Updating first would let an anomaly normalise
        # itself, which is how a slow-escalating actor disappears.
        baseline = await self._baselines.load(run_id, employee_id)
        baseline.archetype = str(actor.get("archetype", "engineer"))
        baseline.observe(facts)
        await self._baselines.save(run_id, baseline)

        await self._maybe_open_incident(run_id, employee_id, composite, facts, events)
        return profile

    def _static_for(self, facts: SessionFacts, actor: dict[str, Any]) -> int:
        """The most sensitive thing attempted in the session."""
        sensitivity = Sensitivity.LOW
        if facts.secret_attempts or facts.prod_attempts:
            sensitivity = Sensitivity.CRITICAL
        elif facts.external_attempts:
            sensitivity = Sensitivity.HIGH
        elif facts.actions_blocked:
            sensitivity = Sensitivity.MEDIUM

        return scoring.static_score(
            role=Role(actor.get("role", Role.ENGINEER)),
            sensitivity=sensitivity,
            prod_access=str(actor.get("prod_access", "none")),
            is_production=facts.prod_attempts > 0,
        )

    async def _maybe_open_incident(
        self,
        run_id: str,
        employee_id: str,
        composite: scoring.CompositeScore,
        facts: SessionFacts,
        events: list[EventEnvelope],
    ) -> None:
        evidence = [
            evidence_from_event(e.detail.payload, e.detail.seq, e.detail.sim_ts)
            for e in events
            if e.detail_type == "gate2.decision"
            and e.detail.payload.get("decision") in ("block", "review")
        ]

        await self._incidents.observe(
            run_id=run_id,
            employee_id=employee_id,
            score=composite.score,
            sim_ts=facts.sim_ts,
            evidence=evidence,
            static_critical=composite.static >= 85 and facts.prod_attempts > 0,
        )

    # ── training ─────────────────────────────────────────────────────

    async def train(self, run_id: str) -> dict[str, Any]:
        """Fit the forest on every scored session in the run.

        Called nightly per simulated day, and by `python tasks.py train-risk`.
        Reads only vectors -- never a label, and there is no code path to one.
        """
        page = await self._store.query(pk=f"RUN#{run_id}", sk_prefix="SESSION#", limit=10_000)
        vectors = [self._features.vector(item.body.get("features", {})) for item in page.items]
        result = self._detector.train(vectors)
        logger.info("risk model trained", extra={"run_id": run_id, **result})
        return result

    # ── persistence ──────────────────────────────────────────────────

    async def _persist(self, run_id: str, profile: RiskProfile) -> None:
        await self._store.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"RISK#{profile.employee_id}",
                gsi1pk=f"RUN#{run_id}#RISKRANK",
                # Zero-padded so the leaderboard is a range query, not a sort.
                gsi1sk=f"{profile.score:03d}#{profile.employee_id}",
                body=profile.model_dump(mode="json"),
            )
        )
        # The session vector, kept for training.
        await self._store.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"SESSION#{profile.updated_sim_ts:010d}#{profile.employee_id}",
                body={
                    "employee_id": profile.employee_id,
                    "sim_ts": profile.updated_sim_ts,
                    "features": profile.features,
                    "score": profile.score,
                },
            )
        )

    async def _actor(self, run_id: str, employee_id: str) -> dict[str, Any]:
        """Enough of the employee record to score against.

        Note what is read: role, team, work hours, archetype. Not
        `scenario_profile` -- it is on the record, and this is the one place
        that could carelessly pick it up, so the projection is explicit.
        """
        if employee_id in self._actors:
            return self._actors[employee_id]

        item = await self._store.get(f"RUN#{run_id}", f"EMP#{employee_id}")
        if item is None:
            return {"role": Role.ENGINEER, "archetype": "engineer", "work_hours": (9, 18)}

        persona = item.body.get("persona", {})
        actor = {
            "role": item.body.get("role", Role.ENGINEER),
            "team": item.body.get("team", ""),
            "archetype": persona.get("archetype", "engineer"),
            "work_hours": tuple(persona.get("work_hours", (9, 18))),
            "prod_access": persona.get("prod_access", "none"),
        }
        self._actors[employee_id] = actor
        return actor

    async def current(self, run_id: str, employee_id: str) -> int:
        """The score a gate reads. Read-only, and never blocks a decision."""
        try:
            item = await self._store.get(f"RUN#{run_id}", f"RISK#{employee_id}")
            return int(item.body.get("score", 0)) if item else 0
        except Exception:
            return 0


def empty_profile(run_id: str, employee_id: str) -> RiskProfile:
    return RiskProfile(
        employee_id=employee_id, run_id=run_id, features=empty_vector(), confidence="low"
    )
