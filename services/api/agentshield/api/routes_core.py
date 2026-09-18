"""Employees, tasks, events, approvals.

Grouped in one module because they share the same read helpers and the same
shape: a list endpoint backed by an enumerated access pattern, and a detail
endpoint that assembles one entity's full trace in a single query.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from agentshield.api.schemas import ApprovalDecisionRequest, ok
from agentshield.deps import Services, get_services
from agentshield.domain.enums import TaskStatus
from agentshield.domain.errors import NotFound
from agentshield.domain.models import (
    AgentAction,
    Approval,
    Employee,
    GateRequest,
    Task,
)
from agentshield.governance.approvals import status_to_task_status
from agentshield.sim.clock import SimClock

employees_router = APIRouter(prefix="/employees", tags=["employees"])
tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])
events_router = APIRouter(prefix="/events", tags=["events"])
approvals_router = APIRouter(prefix="/approvals", tags=["approvals"])


# ──────────────────────────────────────────────────────────────────────
# Employees
# ──────────────────────────────────────────────────────────────────────


@employees_router.get("")
async def list_employees(
    run_id: str,
    team: str | None = None,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """A3 / A5.

    Every record goes through `Employee.to_public()`, which has no
    `scenario_profile` field at the type level. The operator sees what the
    system inferred, never what the simulator was told.
    """
    employees = await services.seeder.load_employees(run_id)
    if team:
        employees = [e for e in employees if e.team == team]

    enriched = []
    for employee in sorted(employees, key=lambda e: e.id):
        public = await _public_employee(services, run_id, employee)
        enriched.append(public.model_dump(mode="json"))
    return ok(enriched)


@employees_router.get("/{employee_id}")
async def get_employee(
    employee_id: str, run_id: str, services: Services = Depends(get_services)
) -> dict[str, Any]:
    employee = await services.seeder.load_employee(run_id, employee_id)
    if employee is None:
        raise NotFound(f"no employee {employee_id!r}")

    public = await _public_employee(services, run_id, employee)
    risk = await services.container.docstore.get(f"RUN#{run_id}", f"RISK#{employee_id}")
    tasks = await _employee_tasks(services, run_id, employee_id, limit=10)
    current = next((t for t in tasks if t.status not in _TERMINAL), None)

    return ok(
        {
            "employee": public.model_dump(mode="json"),
            "risk": risk.body if risk else None,
            "current_task": current.model_dump(mode="json") if current else None,
            "recent_decisions": await _recent_decisions(services, run_id, employee_id),
            "today": public.today.model_dump(mode="json"),
            "seven_day": await _seven_day(services, run_id, employee_id),
        }
    )


_TERMINAL = {
    TaskStatus.COMPLETED,
    TaskStatus.BLOCKED,
    TaskStatus.DENIED,
    TaskStatus.DENIED_TIMEOUT,
    TaskStatus.FAILED,
}


async def _public_employee(services: Services, run_id: str, employee: Employee) -> Any:
    sim_date = _sim_date(services)
    counters = await services.counters.read(run_id, "emp", employee.id, sim_date)
    risk = await services.container.docstore.get(f"RUN#{run_id}", f"RISK#{employee.id}")

    state = services.engine.state(run_id)
    active = state.active.get(employee.id) if state else None

    from agentshield.domain.models import EmployeeDailyCounters

    return employee.to_public(
        status=active.status if active else TaskStatus.QUEUED,
        current_task_id=active.id if active else None,
        risk_score=int(risk.body.get("score", 0)) if risk else 0,
        risk_confidence=str(risk.body.get("confidence", "low")) if risk else "low",  # type: ignore[arg-type]
        today=EmployeeDailyCounters(
            requests=int(counters.get("requests", 0)),
            tokens=int(counters.get("tokens", 0)),
            cost_usd=round(float(counters.get("cost_usd", 0.0)), 4),
            allowed=int(counters.get("allowed", 0)),
            blocked=int(counters.get("blocked", 0)),
            review=int(counters.get("review", 0)),
            redacted=int(counters.get("redacted", 0)),
        ),
    )


async def _recent_decisions(
    services: Services, run_id: str, employee_id: str, limit: int = 10
) -> list[dict[str, Any]]:
    """A12 -- the last governed decisions for one employee."""
    events = await services.emitter.read_page(run_id, employee_id=employee_id, limit=200)
    decisions = [
        {
            "seq": e.detail.seq,
            "sim_ts": e.detail.sim_ts,
            "kind": e.detail_type,
            "tool": e.detail.payload.get("tool"),
            "resource": e.detail.payload.get("target_resource"),
            "decision": e.detail.payload.get("decision"),
            "task_id": e.detail.task_id,
        }
        for e in events
        if e.detail_type in ("gate1.decision", "gate2.decision")
    ]
    return decisions[-limit:][::-1]


async def _seven_day(services: Services, run_id: str, employee_id: str) -> dict[str, Any]:
    """A21, narrowed to one employee's counters."""
    counters = await services.counters.read_dimension(run_id, "emp")
    totals = {"requests": 0, "tokens": 0, "cost_usd": 0.0}
    for key, body in counters.items():
        if not key.startswith(f"{employee_id}#"):
            continue
        totals["requests"] += int(body.get("requests", 0))
        totals["tokens"] += int(body.get("tokens", 0))
        totals["cost_usd"] += float(body.get("cost_usd", 0.0))
    totals["cost_usd"] = round(totals["cost_usd"], 4)
    return totals


# ──────────────────────────────────────────────────────────────────────
# Tasks
# ──────────────────────────────────────────────────────────────────────


@tasks_router.get("")
async def list_tasks(
    run_id: str,
    employee_id: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """A6 / A7 / A8, depending on which filter is supplied."""
    store = services.container.docstore

    if employee_id:
        page = await store.query(
            pk=f"RUN#{run_id}#EMP#{employee_id}",
            index="gsi1",
            sk_prefix="TASK#",
            ascending=False,
            limit=limit,
            cursor=cursor,
        )
    elif status:
        page = await store.query(
            pk=f"RUN#{run_id}#STATUS#{status}",
            index="gsi2",
            ascending=False,
            limit=limit,
            cursor=cursor,
        )
    else:
        page = await store.query(
            pk=f"RUN#{run_id}",
            sk_prefix="TASK#",
            ascending=False,
            limit=limit,
            cursor=cursor,
        )

    return {
        "data": [Task.model_validate(i.body).model_dump(mode="json") for i in page.items],
        "cursor": page.cursor,
    }


@tasks_router.get("/{task_id}")
async def get_task(task_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    """A9 -- the full trace in one query.

    Everything under a task shares its partition key, so META, the Gate 1
    record, every action and every approval come back in a single round trip.
    That is the whole reason for the single-table layout.
    """
    page = await services.container.docstore.query(pk=f"TASK#{task_id}", limit=200)
    if not page.items:
        raise NotFound(f"no task {task_id!r}")

    task: Task | None = None
    gate1: GateRequest | None = None
    actions: list[AgentAction] = []
    approvals: list[Approval] = []

    for item in page.items:
        if item.sk == "META":
            task = Task.model_validate(item.body)
        elif item.sk.startswith("REQ#"):
            gate1 = GateRequest.model_validate(item.body)
        elif item.sk.startswith("ACT#"):
            actions.append(AgentAction.model_validate(item.body))
        elif item.sk.startswith("APPR#"):
            approvals.append(Approval.model_validate(item.body))

    if task is None:
        raise NotFound(f"no task {task_id!r}")

    return ok(
        {
            "task": task.model_dump(mode="json"),
            "gate1": gate1.model_dump(mode="json") if gate1 else None,
            "actions": [a.model_dump(mode="json") for a in sorted(actions, key=lambda a: a.seq)],
            "approvals": [a.model_dump(mode="json") for a in approvals],
            "transcript": [],
        }
    )


async def _employee_tasks(
    services: Services, run_id: str, employee_id: str, limit: int = 10
) -> list[Task]:
    page = await services.container.docstore.query(
        pk=f"RUN#{run_id}#EMP#{employee_id}",
        index="gsi1",
        sk_prefix="TASK#",
        ascending=False,
        limit=limit,
    )
    return [Task.model_validate(i.body) for i in page.items]


# ──────────────────────────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────────────────────────


@events_router.get("")
async def list_events(
    run_id: str,
    since_seq: int = 0,
    type: str | None = None,
    employee_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Initial Live Feed hydration, and WebSocket gap recovery."""
    events = await services.emitter.read_page(
        run_id,
        since_seq=since_seq,
        limit=limit,
        detail_type=type,
        employee_id=employee_id,
    )
    next_seq = events[-1].detail.seq if events else since_seq
    return {
        "data": [e.model_dump(mode="json") for e in events],
        "next_seq": next_seq,
        "has_more": len(events) == limit,
    }


# ──────────────────────────────────────────────────────────────────────
# Approvals
# ──────────────────────────────────────────────────────────────────────


@approvals_router.get("")
async def list_approvals(
    run_id: str,
    status: str = "pending",
    approver_id: str | None = None,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """A13 / A14, enriched into the decision card the manager actually reads.

    The card carries risk, session cost and the requester's seven-day rate for
    this action type, because "approve or deny" without those is a coin flip
    dressed as a control.
    """
    if approver_id:
        approvals = await services.approvals.for_approver(run_id, approver_id)
    elif status == "pending":
        approvals = await services.approvals.pending(run_id)
    else:
        approvals = await services.approvals.decided_today(run_id)

    cards = []
    for approval in approvals:
        requester = await services.seeder.load_employee(run_id, approval.requester_id)
        cards.append(
            {
                "approval": approval.model_dump(mode="json"),
                "requester": {
                    "id": approval.requester_id,
                    "name": requester.name if requester else approval.requester_id,
                    "role": str(requester.role) if requester else "",
                    "team": requester.team if requester else "",
                    "risk_score": approval.risk_at_request,
                    "sprite_key": requester.sprite_key if requester else "char_00",
                },
                "action": {
                    "tool": str(approval.tool) if approval.tool else "",
                    "target_resource": approval.target_resource,
                    "environment": str(approval.environment),
                    "args_preview": approval.args_preview,
                },
                "context": {
                    "reason": approval.reason,
                    "policy_id": approval.policy_id,
                    "cost_so_far_usd": approval.cost_so_far_usd,
                    "session_actions": 0,
                    "requester_7d_rate_for_tool": await _seven_day_tool_rate(
                        services, run_id, approval.requester_id, str(approval.tool or "")
                    ),
                },
            }
        )

    return ok(cards)


@approvals_router.post("/{approval_id}/decide")
async def decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    run_id: str,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    approval = await services.approvals.decide(
        run_id=run_id,
        approval_id=approval_id,
        decision=body.decision,
        approver_id=body.approver_id,
        note=body.note,
    )
    return ok(
        {
            "approval_id": approval.id,
            "status": str(approval.status),
            "task_status": str(status_to_task_status(approval.status)),
            "decided_sim_ts": approval.decided_sim_ts,
        }
    )


async def _seven_day_tool_rate(services: Services, run_id: str, employee_id: str, tool: str) -> int:
    """How often this person normally does this.

    The single most useful number on the card: "Rahul has deployed to prod 0
    times in the last 7 days" is a decision, where a risk score alone is a
    vibe.
    """
    if not tool:
        return 0
    events = await services.emitter.read_page(run_id, employee_id=employee_id, limit=500)
    return sum(
        1
        for e in events
        if e.detail_type == "gate2.decision" and e.detail.payload.get("tool") == tool
    )


def _sim_date(services: Services) -> str:
    clock = services.container.clock
    if isinstance(clock, SimClock):
        return clock.sim_date
    from datetime import UTC, datetime

    return datetime.fromtimestamp(clock.sim_ts, tz=UTC).strftime("%Y-%m-%d")
