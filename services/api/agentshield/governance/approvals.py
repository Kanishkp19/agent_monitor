"""The approval lifecycle.

A `review` decision does not block and does not allow -- it holds, and routes
a decision card to a human. Three properties matter here:

**Terminal states are immutable.** A second decision on the same approval is a
409, not a silent overwrite. An approval record is evidence of who allowed
what, and evidence that can be edited is not evidence.

**Expiry runs on simulated time.** The TTL sweep reads `clock.sim_ts` on every
tick, never wall time. Sweeping on wall time is the documented cause of
approvals that never resolve during a fast-forward.

**`approve_session` is scoped to the task.** It grants the same
tool+resource+environment tuple for the remainder of *that task only*. A grant
that outlived its task would be a standing permission nobody remembers giving.
"""

from __future__ import annotations

import logging
from typing import Any

import ulid

from agentshield.domain.enums import ApprovalStatus, Decision, Role, TaskStatus
from agentshield.domain.errors import ApprovalAlreadyDecided, NotFound
from agentshield.domain.models import ActionContext, Approval, ApproverSpec, Task
from agentshield.ports.clock import ClockPort
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.telemetry.emitter import TelemetryEmitter

logger = logging.getLogger(__name__)

_APPROVED = frozenset({ApprovalStatus.APPROVED_ONCE, ApprovalStatus.APPROVED_SESSION})

_DECISION_TO_STATUS: dict[str, ApprovalStatus] = {
    "approve_once": ApprovalStatus.APPROVED_ONCE,
    "approve_session": ApprovalStatus.APPROVED_SESSION,
    "deny": ApprovalStatus.DENIED,
}


class ApprovalEngine:
    def __init__(
        self,
        *,
        docstore: DocStorePort,
        clock: ClockPort,
        emitter: TelemetryEmitter,
        default_ttl: int = 300,
    ) -> None:
        self._docstore = docstore
        self._clock = clock
        self._emitter = emitter
        self._default_ttl = default_ttl

    # ── request ──────────────────────────────────────────────────────

    async def request(
        self,
        *,
        run_id: str,
        task: Task,
        action_id: str,
        context: ActionContext,
        reason: str,
        policy_id: str,
        approver: ApproverSpec | None,
        ttl_sim_seconds: int | None = None,
    ) -> Approval:
        ttl = ttl_sim_seconds or self._default_ttl
        now = self._clock.sim_ts

        approval = Approval(
            id=f"appr_{ulid.new()}",
            run_id=run_id,
            task_id=task.id,
            action_id=action_id,
            requester_id=task.employee_id,
            approver_role=approver.role if approver else Role.MANAGER,
            approver_scope=approver.scope if approver else "team",
            status=ApprovalStatus.PENDING,
            reason=reason,
            policy_id=policy_id,
            tool=context.tool,
            target_resource=context.target_resource,
            environment=context.environment,
            args_preview=_preview(context.args),
            risk_at_request=context.actor.risk_score,
            cost_so_far_usd=context.cost_so_far_usd,
            requested_sim_ts=now,
            expires_sim_ts=now + ttl,
        )

        await self._persist(approval)
        await self._emitter.emit(
            "approval.requested",
            run_id=run_id,
            employee_id=task.employee_id,
            task_id=task.id,
            payload={
                "approval_id": approval.id,
                "task_id": task.id,
                "action_id": action_id,
                "requester_id": task.employee_id,
                "approver_role": str(approval.approver_role),
                "approver_scope": approval.approver_scope,
                "reason": reason,
                "risk_at_request": approval.risk_at_request,
                "cost_so_far_usd": approval.cost_so_far_usd,
                "expires_sim_ts": approval.expires_sim_ts,
            },
        )
        return approval

    # ── decide ───────────────────────────────────────────────────────

    async def decide(
        self,
        *,
        run_id: str,
        approval_id: str,
        decision: str,
        approver_id: str,
        note: str | None = None,
    ) -> Approval:
        approval = await self.get(run_id, approval_id)

        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecided(
                f"approval {approval_id} is already {approval.status}",
                details={"status": str(approval.status)},
            )

        status = _DECISION_TO_STATUS.get(decision)
        if status is None:
            raise NotFound(f"unknown approval decision {decision!r}")

        now = self._clock.sim_ts
        approval.status = status
        approval.approver_id = approver_id
        approval.note = note
        approval.decided_sim_ts = now

        await self._persist(approval)
        await self._emitter.emit(
            "approval.decided",
            run_id=run_id,
            employee_id=approval.requester_id,
            task_id=approval.task_id,
            payload={
                "approval_id": approval.id,
                "task_id": approval.task_id,
                "status": str(status),
                "approver_id": approver_id,
                "note": note or "",
                "latency_sim_s": now - approval.requested_sim_ts,
            },
        )
        return approval

    # ── expiry ───────────────────────────────────────────────────────

    async def sweep_expired(self, run_id: str) -> list[Approval]:
        """Expire anything past its TTL. Called on every tick.

        Reads `clock.sim_ts`, never wall time -- during a 100x fast-forward,
        wall time barely moves while days of simulated time pass, and an
        approval queue that never drains would deadlock the run.
        """
        now = self._clock.sim_ts
        expired: list[Approval] = []

        for approval in await self.pending(run_id):
            if approval.expires_sim_ts > now:
                continue

            approval.status = ApprovalStatus.EXPIRED
            approval.decided_sim_ts = now
            await self._persist(approval)
            await self._emitter.emit(
                "approval.decided",
                run_id=run_id,
                employee_id=approval.requester_id,
                task_id=approval.task_id,
                payload={
                    "approval_id": approval.id,
                    "task_id": approval.task_id,
                    "status": str(ApprovalStatus.EXPIRED),
                    "approver_id": "",
                    "note": "expired without a decision",
                    "latency_sim_s": now - approval.requested_sim_ts,
                },
            )
            expired.append(approval)

        return expired

    # ── reads ────────────────────────────────────────────────────────

    async def get(self, run_id: str, approval_id: str) -> Approval:
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#APPRID#{approval_id}", index="gsi1", limit=1
        )
        if page.items:
            return Approval.model_validate(page.items[0].body)
        raise NotFound(f"no approval {approval_id!r}")

    async def pending(self, run_id: str) -> list[Approval]:
        """A13 -- the approvals queue."""
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#APPR#{ApprovalStatus.PENDING}", index="gsi1", limit=200
        )
        return [Approval.model_validate(item.body) for item in page.items]

    async def for_approver(self, run_id: str, approver_id: str) -> list[Approval]:
        """A14."""
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#APPROVER#{approver_id}",
            index="gsi2",
            ascending=False,
            limit=100,
        )
        return [Approval.model_validate(item.body) for item in page.items]

    async def for_task(self, task_id: str) -> list[Approval]:
        page = await self._docstore.query(pk=f"TASK#{task_id}", sk_prefix="APPR#", limit=50)
        return [Approval.model_validate(item.body) for item in page.items]

    async def decided_today(self, run_id: str) -> list[Approval]:
        out: list[Approval] = []
        for status in (
            ApprovalStatus.APPROVED_ONCE,
            ApprovalStatus.APPROVED_SESSION,
            ApprovalStatus.DENIED,
            ApprovalStatus.EXPIRED,
        ):
            page = await self._docstore.query(
                pk=f"RUN#{run_id}#APPR#{status}", index="gsi1", ascending=False, limit=100
            )
            out.extend(Approval.model_validate(item.body) for item in page.items)
        out.sort(key=lambda a: a.decided_sim_ts or 0, reverse=True)
        return out

    # ── persistence ──────────────────────────────────────────────────

    async def _persist(self, approval: Approval) -> None:
        body = approval.model_dump(mode="json")
        ts = f"{approval.requested_sim_ts:010d}"
        await self._docstore.put(
            DocItem(
                pk=f"TASK#{approval.task_id}",
                sk=f"APPR#{approval.id}",
                gsi1pk=f"RUN#{approval.run_id}#APPR#{approval.status}",
                gsi1sk=ts,
                gsi2pk=(
                    f"RUN#{approval.run_id}#APPROVER#{approval.approver_id}"
                    if approval.approver_id
                    else None
                ),
                gsi2sk=ts if approval.approver_id else None,
                body=body,
            )
        )
        # A direct lookup by approval id. `POST /approvals/{id}/decide` knows
        # the approval id and nothing else, and scanning to find its task
        # would be exactly the access pattern this store forbids.
        await self._docstore.put(
            DocItem(
                pk=f"APPRIDX#{approval.id}",
                sk="META",
                gsi1pk=f"RUN#{approval.run_id}#APPRID#{approval.id}",
                gsi1sk=ts,
                body=body,
            )
        )


def status_to_task_status(status: ApprovalStatus) -> TaskStatus:
    """What an approval outcome does to the task waiting on it."""
    if status in _APPROVED:
        return TaskStatus.WORKING
    if status is ApprovalStatus.DENIED:
        return TaskStatus.DENIED
    return TaskStatus.DENIED_TIMEOUT


def was_approved(status: ApprovalStatus) -> bool:
    return status in _APPROVED


def decision_for(status: ApprovalStatus) -> Decision:
    return Decision.ALLOW if was_approved(status) else Decision.BLOCK


def _preview(args: dict[str, Any]) -> str:
    """A short, safe rendering of tool arguments for the approval card.

    Truncated hard: an approver needs to know what is about to be touched,
    not to read a diff. Long values are elided rather than wrapped.
    """
    parts = []
    for key, value in sorted(args.items()):
        text = str(value)
        if len(text) > 60:
            text = text[:57] + "..."
        parts.append(f"{key}={text}")
    preview = " ".join(parts)
    return preview[:200]
