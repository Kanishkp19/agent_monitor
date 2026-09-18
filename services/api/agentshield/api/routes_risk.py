"""Risk and incidents.

The `/explain` endpoint is the point of this router. A risk score without its
reasons is a black box replacing a black box, and the wording of those reasons
lives in `risk/scoring.py` -- not here, and not in the client -- so the API,
the employee drawer and `/control/risk` can never phrase the same factor three
different ways.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from agentshield.api.schemas import ok
from agentshield.deps import Services, get_services
from agentshield.domain.errors import NotFound
from agentshield.domain.models import Incident, RiskProfile

router = APIRouter(tags=["risk"])


@router.get("/risk/employees")
async def risk_leaderboard(
    run_id: str,
    team: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """A15 -- ranked by score, descending."""
    page = await services.container.docstore.query(
        pk=f"RUN#{run_id}#RISKRANK", index="gsi1", ascending=False, limit=limit * 2
    )
    profiles = [RiskProfile.model_validate(i.body) for i in page.items]

    if team:
        employees = await services.seeder.load_employees(run_id)
        members = {e.id for e in employees if e.team == team}
        profiles = [p for p in profiles if p.employee_id in members]

    return ok([p.model_dump(mode="json") for p in profiles[:limit]])


@router.get("/risk/employees/{employee_id}/explain")
async def explain_risk(
    employee_id: str, run_id: str, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Why this person scores what they score.

    Top three factors in plain language, the baseline each is measured
    against, and the events that contributed. Never the scenario label -- the
    operator sees what the system inferred, and the system was never told.
    """
    item = await services.container.docstore.get(f"RUN#{run_id}", f"RISK#{employee_id}")
    if item is None:
        raise NotFound(f"no risk profile for {employee_id!r}")

    profile = RiskProfile.model_validate(item.body)
    baselines = await _baseline_comparison(services, run_id, employee_id, profile)
    contributors = await _recent_contributors(services, run_id, employee_id)

    return ok(
        {
            "employee_id": profile.employee_id,
            "score": profile.score,
            "static": profile.static,
            "behavioural": profile.behavioural,
            "ml": profile.ml,
            "confidence": profile.confidence,
            "sessions_observed": profile.sessions_observed,
            "top_factors": [f.model_dump(mode="json") for f in profile.top_factors],
            "baseline": baselines,
            "recent_contributors": contributors,
        }
    )


@router.get("/risk/weights")
async def risk_weights(services: Services = Depends(get_services)) -> dict[str, Any]:
    """The blend, surfaced read-only.

    Shown in the Control Center so a demo can point at the three terms rather
    than assert them.
    """
    settings = services.container.settings
    return ok(
        {
            "static": settings.risk_weight_static,
            "behavioural": settings.risk_weight_behavioural,
            "ml": settings.risk_weight_ml,
            "incident_threshold": settings.risk_incident_threshold,
            "baseline_window_days": settings.risk_baseline_window_days,
            "min_sessions_for_baseline": settings.risk_min_sessions_for_baseline,
        }
    )


@router.get("/incidents")
async def list_incidents(
    run_id: str,
    status: str = "open",
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """A17."""
    page = await services.container.docstore.query(
        pk=f"RUN#{run_id}#INC#{status}", index="gsi1", ascending=False, limit=100
    )
    return ok([Incident.model_validate(i.body).model_dump(mode="json") for i in page.items])


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: str, run_id: str, services: Services = Depends(get_services)
) -> dict[str, Any]:
    item = await services.container.docstore.get(f"RUN#{run_id}", f"INC#{incident_id}")
    if item is None:
        raise NotFound(f"no incident {incident_id!r}")

    incident = Incident.model_validate(item.body)
    incident.status = "acknowledged"

    from agentshield.ports.docstore import DocItem

    await services.container.docstore.put(
        DocItem(
            pk=f"RUN#{run_id}",
            sk=f"INC#{incident.id}",
            gsi1pk=f"RUN#{run_id}#INC#acknowledged",
            gsi1sk=f"{incident.opened_sim_ts:010d}",
            body=incident.model_dump(mode="json"),
        )
    )
    return ok(incident.model_dump(mode="json"))


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _baseline_comparison(
    services: Services, run_id: str, employee_id: str, profile: RiskProfile
) -> list[dict[str, Any]]:
    """Baseline versus now, for the three features that moved most.

    "tokens/session 4,100 ± 900 -> 23,800" is the sentence that makes a risk
    score arguable rather than oracular.
    """
    item = await services.container.docstore.get(f"RUN#{run_id}", f"BASELINE#{employee_id}")
    if item is None:
        return []

    stats = item.body.get("features", {})
    out = []
    for feature, current in profile.features.items():
        stat = stats.get(feature)
        if not isinstance(stat, dict):
            continue
        out.append(
            {
                "feature": feature,
                "mean": round(float(stat.get("mean", 0.0)), 4),
                "std": round(float(stat.get("std", 0.0)), 4),
                "current": round(float(current), 4),
            }
        )
    return out


async def _recent_contributors(
    services: Services, run_id: str, employee_id: str, limit: int = 8
) -> list[dict[str, Any]]:
    events = await services.emitter.read_page(run_id, employee_id=employee_id, limit=200)
    contributors = [
        {
            "event_seq": e.detail.seq,
            "sim_ts": e.detail.sim_ts,
            "kind": str(e.detail.payload.get("tool") or e.detail_type),
            "detail": (
                f"{e.detail.payload.get('target_resource', '')} "
                f"{str(e.detail.payload.get('decision', '')).upper()}"
            ).strip(),
        }
        for e in events
        if e.detail_type == "gate2.decision"
        and e.detail.payload.get("decision") in ("block", "review")
    ]
    return contributors[-limit:][::-1]
