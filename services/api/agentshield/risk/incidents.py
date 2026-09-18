"""Incident open, merge and close.

An incident opens when composite risk crosses 70 for two consecutive sessions,
or when any single static-critical event occurs. The "two consecutive" rule is
what stops a one-off spike -- a genuinely unusual Tuesday -- from paging
someone; the static-critical rule is what stops that patience from applying to
an intern deploying to production.

Subsequent qualifying events within 24 simulated hours **merge** into the open
incident rather than opening new ones. Without that, the adversarial ladder
would produce forty incidents for one actor and the list would be unusable
exactly when it mattered.
"""

from __future__ import annotations

import logging
from typing import Any

import ulid

from agentshield.domain.models import Incident, IncidentEvidence
from agentshield.ports.docstore import DocItem, DocStorePort

logger = logging.getLogger(__name__)

MERGE_WINDOW_SIM_SECONDS = 24 * 3600
CONSECUTIVE_SESSIONS_REQUIRED = 2
MAX_EVIDENCE = 40


class IncidentManager:
    def __init__(self, docstore: DocStorePort, *, threshold: int = 70) -> None:
        self._docstore = docstore
        self._threshold = threshold
        self._consecutive: dict[str, int] = {}

    async def observe(
        self,
        *,
        run_id: str,
        employee_id: str,
        score: int,
        sim_ts: int,
        evidence: list[IncidentEvidence],
        detector: str = "composite",
        static_critical: bool = False,
    ) -> Incident | None:
        """Consider one scored session. Returns an incident if one opened."""
        if static_critical:
            # No patience for these. A critical static event is wrong on its
            # own terms, and waiting for a second one would mean waiting for a
            # second production deploy by someone who may not deploy at all.
            return await self._open_or_merge(
                run_id=run_id,
                employee_id=employee_id,
                score=score,
                sim_ts=sim_ts,
                evidence=evidence,
                detector="static_critical",
            )

        if score < self._threshold:
            self._consecutive[employee_id] = 0
            return None

        self._consecutive[employee_id] = self._consecutive.get(employee_id, 0) + 1
        if self._consecutive[employee_id] < CONSECUTIVE_SESSIONS_REQUIRED:
            return None

        return await self._open_or_merge(
            run_id=run_id,
            employee_id=employee_id,
            score=score,
            sim_ts=sim_ts,
            evidence=evidence,
            detector=detector,
        )

    async def _open_or_merge(
        self,
        *,
        run_id: str,
        employee_id: str,
        score: int,
        sim_ts: int,
        evidence: list[IncidentEvidence],
        detector: str,
    ) -> Incident | None:
        existing = await self._open_for(run_id, employee_id)

        if existing and sim_ts - existing.last_seen_sim_ts <= MERGE_WINDOW_SIM_SECONDS:
            existing.last_seen_sim_ts = sim_ts
            existing.score = max(existing.score, score)
            # Evidence is capped. An incident that accumulated four hundred
            # rows would be technically complete and practically unreadable.
            existing.evidence = (existing.evidence + evidence)[-MAX_EVIDENCE:]
            existing.summary = _summarise(existing.evidence, existing.score)
            await self._persist(run_id, existing)
            return None

        incident = Incident(
            id=f"inc_{ulid.new().str[-6:].lower()}",
            run_id=run_id,
            employee_id=employee_id,
            detector=detector,
            score=score,
            opened_sim_ts=sim_ts,
            last_seen_sim_ts=sim_ts,
            status="open",
            evidence=evidence[-MAX_EVIDENCE:],
            summary=_summarise(evidence, score),
        )
        await self._persist(run_id, incident)
        logger.info(
            "incident opened",
            extra={"incident_id": incident.id, "employee_id": employee_id, "score": score},
        )
        return incident

    async def _open_for(self, run_id: str, employee_id: str) -> Incident | None:
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#INC#open", index="gsi1", ascending=False, limit=50
        )
        for item in page.items:
            if item.body.get("employee_id") == employee_id:
                return Incident.model_validate(item.body)
        return None

    async def _persist(self, run_id: str, incident: Incident) -> None:
        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"INC#{incident.id}",
                gsi1pk=f"RUN#{run_id}#INC#{incident.status}",
                gsi1sk=f"{incident.opened_sim_ts:010d}",
                body=incident.model_dump(mode="json"),
            )
        )

    async def close(self, run_id: str, incident_id: str) -> Incident | None:
        item = await self._docstore.get(f"RUN#{run_id}", f"INC#{incident_id}")
        if item is None:
            return None
        incident = Incident.model_validate(item.body)
        incident.status = "closed"
        await self._persist(run_id, incident)
        return incident


def _summarise(evidence: list[IncidentEvidence], score: int) -> str:
    """A one-line description built from what actually happened.

    Never from the scenario label -- the detector was not told, and the
    incident must read as something the system worked out.
    """
    if not evidence:
        return f"Composite risk reached {score}."

    kinds: dict[str, int] = {}
    for item in evidence:
        kinds[item.kind] = kinds.get(item.kind, 0) + 1

    parts = [f"{count} {kind}" for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1])[:3]]
    return f"Risk {score}: " + ", ".join(parts)


def evidence_from_event(payload: dict[str, Any], seq: int, sim_ts: int) -> IncidentEvidence:
    tool = str(payload.get("tool", ""))
    resource = str(payload.get("target_resource", ""))
    decision = str(payload.get("decision", "")).upper()
    return IncidentEvidence(
        event_seq=seq,
        sim_ts=sim_ts,
        kind=f"{tool} {decision}".strip().lower() or "event",
        detail=f"{tool} {resource} {decision}".strip(),
    )
