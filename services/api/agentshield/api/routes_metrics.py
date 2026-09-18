"""Metrics: the exec summary and the spend breakdown.

Every figure here is read from counters maintained on write. Nothing scans.
The "waste prevented" number uses the definition in
`docs/05-BACKEND-SCHEMA.md` section 4 and nowhere else, so the UI and the API
cannot disagree about what it means -- which matters when it is on screen
during a demo and someone asks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from agentshield.api.schemas import ok
from agentshield.deps import Services, get_services
from agentshield.sim.clock import SimClock
from agentshield.sim.seed_data import TEAMS

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
async def summary(
    run_id: str,
    scope: str = Query("exec", pattern="^(exec|security)$"),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    sim_date = _sim_date(services)

    run_totals = await services.counters.read(run_id, "run", "", sim_date)
    team_counters = await services.counters.read_dimension(run_id, "team")
    waste_counters = await services.counters.read_dimension(run_id, "waste")
    employees = await services.seeder.load_employees(run_id)

    spend_by_team = _group_by_key(team_counters, "cost_usd")
    risk_by_team = await _risk_by_team(services, run_id, employees)

    incidents = await services.container.docstore.query(
        pk=f"RUN#{run_id}#INC#open", index="gsi1", limit=100
    )

    return ok(
        {
            "employees_enabled": len(employees),
            "requests_today": int(run_totals.get("requests", 0)),
            "spend_today_usd": round(float(run_totals.get("cost_usd", 0.0)), 2),
            "waste_prevented_usd": round(
                sum(float(b.get("waste_usd", 0.0)) for b in waste_counters.values()), 2
            ),
            "blocked_actions": int(run_totals.get("blocked", 0)),
            "approvals_today": int(run_totals.get("review", 0)),
            "high_risk_sessions": await _high_risk_count(services, run_id),
            "open_incidents": incidents.count,
            "spend_by_team": [
                {"team": team, "usd": round(usd, 2)}
                for team, usd in sorted(spend_by_team.items(), key=lambda kv: -kv[1])
            ],
            "risk_by_team": risk_by_team,
            "trend_7d": _trend(team_counters),
            "why_high": await _why_high(services, run_id, risk_by_team),
        }
    )


@router.get("/spend")
async def spend(
    run_id: str,
    group_by: str = Query("team", pattern="^(team|employee|model)$"),
    days: int = Query(7, ge=1, le=30),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    dimension = {"team": "team", "employee": "emp", "model": "model"}[group_by]
    counters = await services.counters.read_dimension(run_id, dimension)
    waste = await services.counters.read_dimension(run_id, "waste")
    total_waste = sum(float(b.get("waste_usd", 0.0)) for b in waste.values())

    grouped: dict[str, dict[str, float]] = {}
    for key, body in counters.items():
        name = key.split("#", 1)[0]
        bucket = grouped.setdefault(name, {"usd": 0.0, "tokens": 0.0})
        bucket["usd"] += float(body.get("cost_usd", 0.0))
        bucket["tokens"] += float(body.get("tokens", 0) or body.get("tokens_in", 0))

    total_spend = sum(b["usd"] for b in grouped.values()) or 1.0

    series = [
        {
            "key": name,
            "usd": round(bucket["usd"], 2),
            "tokens": int(bucket["tokens"]),
            # Waste is apportioned by spend share. The exact attribution lives
            # on the task, but at this granularity a proportional split is
            # honest and avoids a second pass over every session.
            "waste_usd": round(total_waste * (bucket["usd"] / total_spend), 2),
        }
        for name, bucket in sorted(grouped.items(), key=lambda kv: -kv[1]["usd"])
    ]

    return ok({"group_by": group_by, "days": days, "series": series})


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _group_by_key(counters: dict[str, dict[str, Any]], field: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for key, body in counters.items():
        name = key.split("#", 1)[0]
        grouped[name] = grouped.get(name, 0.0) + float(body.get(field, 0.0))
    return grouped


async def _risk_by_team(
    services: Services, run_id: str, employees: list[Any]
) -> list[dict[str, Any]]:
    """Team risk is the max of its members, not the mean.

    A mean hides exactly the case this product exists to find: one compromised
    account on a team of twelve normal ones averages away to nothing.
    """
    page = await services.container.docstore.query(pk=f"RUN#{run_id}", sk_prefix="RISK#", limit=100)
    scores = {i.sk.removeprefix("RISK#"): i.body for i in page.items}
    team_of = {e.id: e.team for e in employees}

    peak: dict[str, tuple[int, str]] = {}
    for employee_id, body in scores.items():
        team = team_of.get(employee_id)
        if not team:
            continue
        score = int(body.get("score", 0))
        if score > peak.get(team, (0, ""))[0]:
            peak[team] = (score, employee_id)

    out = []
    for team in TEAMS:
        score, _ = peak.get(team, (0, ""))
        out.append(
            {
                "team": team,
                "level": "high" if score >= 70 else "medium" if score >= 40 else "low",
                "score": score,
                "drivers": [],
            }
        )
    return sorted(out, key=lambda r: -int(r["score"]))


async def _high_risk_count(services: Services, run_id: str) -> int:
    page = await services.container.docstore.query(pk=f"RUN#{run_id}", sk_prefix="RISK#", limit=100)
    return sum(1 for i in page.items if int(i.body.get("score", 0)) >= 70)


def _trend(team_counters: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, float]] = {}
    for key, body in team_counters.items():
        _, _, sim_date = key.partition("#")
        if not sim_date:
            continue
        bucket = by_date.setdefault(sim_date, {"spend_usd": 0.0, "blocked": 0, "approvals": 0})
        bucket["spend_usd"] += float(body.get("cost_usd", 0.0))
        bucket["blocked"] += int(body.get("blocked", 0))
        bucket["approvals"] += int(body.get("review", 0))

    return [
        {
            "sim_date": date,
            "spend_usd": round(bucket["spend_usd"], 2),
            "blocked": int(bucket["blocked"]),
            "approvals": int(bucket["approvals"]),
        }
        for date, bucket in sorted(by_date.items())[-7:]
    ]


async def _why_high(
    services: Services, run_id: str, risk_by_team: list[dict[str, Any]]
) -> dict[str, Any]:
    """The "why is Payments high?" panel.

    Named evidence, not a number. `docs/01-PRD.md` is explicit that the CTO's
    complaint about every other dashboard is that the number means nothing.
    """
    if not risk_by_team or risk_by_team[0]["level"] == "low":
        return {"team": None, "reasons": []}

    team = str(risk_by_team[0]["team"])
    employees = await services.seeder.load_employees(run_id)
    member_ids = {e.id for e in employees if e.team == team}

    prod_attempts = 0
    offhours = 0
    secret_attempts = 0
    blocked = 0

    events = await services.emitter.read_page(run_id, detail_type="gate2.decision", limit=500)
    for event in events:
        if event.detail.employee_id not in member_ids:
            continue
        payload = event.detail.payload
        if payload.get("environment") == "production":
            prod_attempts += 1
        if payload.get("decision") == "block":
            blocked += 1
        if ".env" in str(payload.get("target_resource", "")):
            secret_attempts += 1

    reasons = []
    if prod_attempts:
        reasons.append(f"{prod_attempts} production access attempts")
    if offhours:
        reasons.append(f"unusual late-night activity ({offhours} sessions after 01:00)")
    if secret_attempts:
        reasons.append(f"{secret_attempts} secret-file access attempts, blocked")
    if blocked:
        reasons.append(f"{blocked} blocked actions")

    return {"team": team, "reasons": reasons}


def _sim_date(services: Services) -> str:
    clock = services.container.clock
    if isinstance(clock, SimClock):
        return clock.sim_date
    from datetime import UTC, datetime

    return datetime.fromtimestamp(clock.sim_ts, tz=UTC).strftime("%Y-%m-%d")
