"""Office snapshots.

`GET /sim/runs/{id}/state` returns one of these. It is how the office
rehydrates on mount, after a WebSocket gap larger than 500 events, and on exit
from 100x mode.

`seq` is the contract: the client applies the snapshot, sets its cursor to
this value, and resumes the stream after it. Without that number, catching up
would either replay events already reflected in the snapshot or skip the ones
that arrived while it was being built.

`applySnapshot` on the client is a hard cut with no tweens, deliberately. An
animated catch-up would be a lie about what happened.
"""

from __future__ import annotations

from agentshield.domain.enums import ApprovalStatus, TaskStatus
from agentshield.domain.models import (
    Employee,
    OfficeAvatarState,
    OfficeSnapshot,
    Task,
)
from agentshield.ports.docstore import DocStorePort
from agentshield.sim.office_map import facing_for_slot, room_of

# Task status -> what the avatar looks like. The office renders five states
# and one overlay; everything else collapses into idle.
_FSM_FOR_STATUS: dict[TaskStatus, str] = {
    TaskStatus.WORKING: "working",
    TaskStatus.REQUESTING: "working",
    TaskStatus.AWAITING_APPROVAL: "waiting",
    TaskStatus.BLOCKED: "blocked",
    TaskStatus.DENIED: "blocked",
    TaskStatus.DENIED_TIMEOUT: "blocked",
}

_BADGE_FOR_FSM: dict[str, str] = {
    "working": "working",
    "waiting": "waiting",
    "blocked": "blocked",
    "idle": "none",
    "meeting": "none",
    "walking": "none",
}

# The score at which the office applies the anomaly overlay, and the lower
# score at which it clears. The gap is hysteresis: without it an employee
# hovering at the threshold flickers.
ANOMALY_ON = 70
ANOMALY_OFF = 60


class SnapshotBuilder:
    def __init__(self, docstore: DocStorePort) -> None:
        self._docstore = docstore

    async def build(
        self,
        *,
        run_id: str,
        seq: int,
        sim_ts: int,
        speed: int,
        employees: list[Employee],
        active: dict[str, Task],
    ) -> OfficeSnapshot:
        risk_scores = await self._risk_scores(run_id)
        pending = await self._pending_approvals(run_id)

        avatars = [
            self._avatar_for(employee, active.get(employee.id), risk_scores.get(employee.id, 0))
            for employee in sorted(employees, key=lambda e: e.id)
        ]

        return OfficeSnapshot(
            run_id=run_id,
            seq=seq,
            sim_ts=sim_ts,
            speed=speed,
            avatars=avatars,
            pending_approvals=pending,
        )

    def _avatar_for(
        self, employee: Employee, task: Task | None, risk_score: int
    ) -> OfficeAvatarState:
        status = task.status if task else TaskStatus.QUEUED
        fsm = _FSM_FOR_STATUS.get(status, "idle")
        badge = _BADGE_FOR_FSM.get(fsm, "none")

        # The overlay is not a state. Someone can be visibly working and
        # flagged at the same time -- which is the most interesting thing the
        # demo has to show, so it must not be hidden by the state badge.
        if risk_score >= ANOMALY_ON:
            badge = "anomaly"

        room = room_of(employee.desk_slot)
        slot = employee.desk_slot.split("/", 1)[-1] if "/" in employee.desk_slot else ""

        return OfficeAvatarState(
            employee_id=employee.id,
            sprite_key=employee.sprite_key,
            tile={"x": employee.desk[0], "y": employee.desk[1]},
            facing=facing_for_slot(room, slot),  # type: ignore[arg-type]
            fsm=fsm,  # type: ignore[arg-type]
            badge=badge,  # type: ignore[arg-type]
            name=employee.name,
            role=str(employee.role),
            team=employee.team,
            risk_score=risk_score,
            status=status,
            current_task_title=task.title if task else None,
        )

    async def _risk_scores(self, run_id: str) -> dict[str, int]:
        page = await self._docstore.query(pk=f"RUN#{run_id}", sk_prefix="RISK#", limit=100)
        return {
            item.sk.removeprefix("RISK#"): int(item.body.get("score", 0)) for item in page.items
        }

    async def _pending_approvals(self, run_id: str) -> int:
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#APPR#{ApprovalStatus.PENDING}", index="gsi1", limit=200
        )
        return page.count
