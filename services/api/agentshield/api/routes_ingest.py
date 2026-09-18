"""Live Mode: the same gates, over HTTP.

This is where mode parity is either real or a marketing claim. These handlers
build a `RequestContext` / `ActionContext` and call `gate1.evaluate()` and
`gate2.evaluate()` -- the identical functions the simulator calls. There is no
parallel implementation to drift.

Two security properties:

**The caller cannot assert its own role.** The bearer token maps server-side
to an `actor_id`, and the role comes from that registered identity. A body
field claiming `role: devops` would be ignored, and there is no such field.

**`source` never reaches a policy.** It is telemetry metadata only, excluded
from both field allowlists, so no rule can behave differently for a real agent
than for a simulated one.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

import ulid
from fastapi import APIRouter, Depends, Header

from agentshield.agent.router import cost_of, estimate_tokens, route
from agentshield.api.schemas import (
    IngestEventRequest,
    IngestGate1Request,
    IngestGate2Request,
    ok,
)
from agentshield.deps import Services, get_services
from agentshield.domain.enums import Decision, Environment, Source, TaskStatus
from agentshield.domain.errors import NotFound, RateLimited, Unauthorized
from agentshield.domain.generated_events import EVENT_TYPES
from agentshield.domain.models import (
    ActionContext,
    ActorContext,
    RequestContext,
    Task,
    digest_args,
)
from agentshield.governance.gate2 import resolve_resource
from agentshield.governance.redaction import raw_prompt_key, to_event_findings
from agentshield.ports.docstore import DocItem
from agentshield.sim.seed_data import protected_branches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["live-mode"])

# 100 requests per second per token, per `docs/05-BACKEND-SCHEMA.md` 6.10.
RATE_LIMIT = 100
RATE_WINDOW_SECONDS = 1.0

_requests: dict[str, deque[float]] = defaultdict(deque)


async def authenticate(
    authorization: str = Header(default=""),
    services: Services = Depends(get_services),
) -> str:
    """Resolve a bearer token to an actor id.

    The mapping is server-side configuration. This is a v1 stand-in for real
    auth, but the property that matters is already correct: identity is
    asserted by the deployment, not by the caller.
    """
    settings = services.container.settings
    if not settings.ingest_enabled:
        raise Unauthorized("Live Mode ingest is disabled.")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise Unauthorized("Missing bearer token.")

    actor_id = settings.ingest_tokens.get(token)
    if not actor_id:
        raise Unauthorized("Unknown token.")

    _enforce_rate_limit(token)
    return actor_id


def _enforce_rate_limit(token: str) -> None:
    now = time.monotonic()
    window = _requests[token]
    while window and now - window[0] > RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= RATE_LIMIT:
        raise RateLimited(f"Over {RATE_LIMIT} requests/second for this token.")
    window.append(now)


# ──────────────────────────────────────────────────────────────────────
# Gate 1
# ──────────────────────────────────────────────────────────────────────


@router.post("/gate1")
async def ingest_gate1(
    body: IngestGate1Request,
    run_id: str,
    actor_id: str = Depends(authenticate),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    employee = await services.seeder.load_employee(run_id, actor_id)
    if employee is None:
        raise NotFound(f"no registered actor {actor_id!r}")

    actor = await _actor_context(services, run_id, employee)
    settings = services.container.settings

    est_in, est_out = estimate_tokens(body.task_type, body.complexity, len(body.prompt))
    routed = route(body.complexity, provider=settings.llm_provider, requested=body.requested_model)

    task = Task(
        id=f"task_{ulid.new().str[-8:].lower()}",
        run_id=run_id,
        employee_id=actor_id,
        title=body.task_ref,
        task_type=body.task_type,  # type: ignore[arg-type]
        complexity=body.complexity,
        repo=body.repo,
        environment=Environment(body.environment),
        status=TaskStatus.REQUESTING,
        started_sim_ts=services.container.clock.sim_ts,
        prompt_text=body.prompt,
        # The one field that differs between modes. Telemetry only.
        source=Source.LIVE,
    )

    context = RequestContext(
        source=Source.LIVE,
        actor=actor,
        task_id=task.id,
        task_type=body.task_type,  # type: ignore[arg-type]
        complexity=body.complexity,
        repo=body.repo,
        environment=Environment(body.environment),
        prompt_text=body.prompt,
        prompt_len=len(body.prompt),
        requested_model=body.requested_model,
        est_input_tokens=est_in,
        est_output_tokens=est_out,
        est_cost_usd=cost_of(routed, est_in, est_out),
        routed_model=routed,
        off_hours=False,
        sim_ts=services.container.clock.sim_ts,
    )

    # The identical call the simulator makes. Not a wrapper around it.
    result = await services.gate1.evaluate(context, run_id=run_id, sim_date=_sim_date(services))

    if result.route_override:
        routed = route(
            body.complexity,
            provider=settings.llm_provider,
            override=result.route_override,
        )
        context.routed_model = routed
        context.est_cost_usd = cost_of(routed, est_in, est_out)

    prompt_out = body.prompt
    if result.redacted_text is not None:
        prompt_out = result.redacted_text
        task.prompt_text = result.redacted_text
        await services.container.blobs.put_object(
            raw_prompt_key(task.id), body.prompt.encode(), "application/json"
        )

    await services.container.docstore.put(
        DocItem(pk=f"TASK#{task.id}", sk="META", body=task.model_dump(mode="json"))
    )

    request_id = f"req_{task.id}"
    await services.emitter.emit(
        "gate1.decision",
        run_id=run_id,
        employee_id=actor_id,
        task_id=task.id,
        payload={
            "task_id": task.id,
            "request_id": request_id,
            "decision": str(result.decision),
            "reason_code": result.reason_code,
            "matched_policies": [m.model_dump(mode="json") for m in result.matched_policies],
            "est_input_tokens": est_in,
            "est_output_tokens": est_out,
            "est_cost_usd": context.est_cost_usd,
            "routed_model": routed,
            "findings": to_event_findings(context.findings),
            "budget_remaining_usd": max(0.0, actor.daily_budget_usd - actor.spend_today_usd),
            "latency_ms": result.latency_ms,
        },
    )

    return ok(
        {
            "decision": str(result.decision),
            "reason": result.message or result.reason_code,
            "policy_ids": [m.policy_id for m in result.matched_policies],
            "routed_model": routed,
            "est_cost_usd": round(context.est_cost_usd, 6),
            "prompt": prompt_out,
            "approval_id": result.approval_id,
            "task_id": task.id,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Gate 2
# ──────────────────────────────────────────────────────────────────────


@router.post("/gate2")
async def ingest_gate2(
    body: IngestGate2Request,
    run_id: str,
    actor_id: str = Depends(authenticate),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    employee = await services.seeder.load_employee(run_id, actor_id)
    if employee is None:
        raise NotFound(f"no registered actor {actor_id!r}")

    item = await services.container.docstore.get(f"TASK#{body.task_id}", "META")
    if item is None:
        raise NotFound(f"no task {body.task_id!r}")
    task = Task.model_validate(item.body)

    actor = await _actor_context(services, run_id, employee)
    resolved = resolve_resource(
        body.tool,
        body.args,
        repo=task.repo,
        environment=task.environment,
        allowed_repositories=actor.allowed_repositories,
        protected_branches=protected_branches(str(body.args.get("repo") or task.repo)),
    )

    context = ActionContext(
        source=Source.LIVE,
        actor=actor,
        task_id=task.id,
        repo=str(resolved["repo"]),
        environment=Environment(str(resolved["environment"])),
        tokens_so_far=task.tokens_in + task.tokens_out,
        cost_so_far_usd=task.cost_usd,
        actions_so_far=task.actions_total,
        blocked_so_far=task.actions_blocked,
        tool=body.tool,
        args=body.args,
        args_digest=digest_args(body.tool, body.args),
        target_resource=str(resolved["target_resource"]),
        resource_sensitivity=resolved["resource_sensitivity"],  # type: ignore[arg-type]
        is_repo_in_scope=bool(resolved["is_repo_in_scope"]),
        is_secret_path=bool(resolved["is_secret_path"]),
        is_protected_branch=bool(resolved["is_protected_branch"]),
        is_external_host=bool(resolved["is_external_host"]),
        iteration_index=body.iteration,
        sim_ts=services.container.clock.sim_ts,
    )

    result = await services.gate2.evaluate(context)

    action_id = f"act_{ulid.new()}"
    approval_id: str | None = None

    if result.decision is Decision.REVIEW:
        attributed = result.matched_policies[0] if result.matched_policies else None
        approval = await services.approvals.request(
            run_id=run_id,
            task=task,
            action_id=action_id,
            context=context,
            reason=result.message or "This action needs approval.",
            policy_id=attributed.policy_id if attributed else "",
            approver=services.gate2.approver_for(attributed),
            ttl_sim_seconds=services.gate2.ttl_for(attributed, 300),
        )
        approval_id = approval.id

    await services.emitter.emit(
        "gate2.decision",
        run_id=run_id,
        employee_id=actor_id,
        task_id=task.id,
        payload={
            "task_id": task.id,
            "action_id": action_id,
            "tool": str(body.tool),
            "decision": str(result.decision),
            "reason_code": result.reason_code,
            "matched_policies": [m.model_dump(mode="json") for m in result.matched_policies],
            "target_resource": context.target_resource,
            "environment": str(context.environment),
            "repeat_count_5m": context.repeat_count_5m,
            "latency_ms": result.latency_ms,
        },
    )

    return ok(
        {
            "decision": str(result.decision),
            "reason": result.message or result.reason_code,
            "policy_ids": [m.policy_id for m in result.matched_policies],
            "approval_id": approval_id,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Events
# ──────────────────────────────────────────────────────────────────────


@router.post("/events", status_code=202)
async def ingest_event(
    body: IngestEventRequest,
    run_id: str,
    actor_id: str = Depends(authenticate),
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    """Accept telemetry from a real agent.

    Validated against the schema registry generated from
    `packages/contracts/events.schema.json`, never against a hardcoded count
    (see `docs/DECISIONS-RESOLVED.md` C1).
    """
    if body.detail_type not in EVENT_TYPES:
        raise NotFound(
            f"unknown event type {body.detail_type!r}",
            details={"known": sorted(EVENT_TYPES)},
        )

    envelope = await services.emitter.emit(
        body.detail_type,
        run_id=run_id,
        employee_id=actor_id,
        task_id=body.task_id,
        payload=body.payload,
    )
    return ok({"seq": envelope.detail.seq})


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _actor_context(services: Services, run_id: str, employee: Any) -> ActorContext:
    """Build the actor from the *registered* identity.

    Everything here comes from the employee record and the counters. Nothing
    comes from the request body, which is what makes role escalation by a
    compromised agent impossible rather than merely discouraged.
    """
    sim_date = _sim_date(services)
    counters = await services.counters.read(run_id, "emp", employee.id, sim_date)
    risk = await services.container.docstore.get(f"RUN#{run_id}", f"RISK#{employee.id}")

    return ActorContext(
        id=employee.id,
        role=employee.role,
        team=employee.team,
        seniority=employee.persona.experience,
        allowed_repositories=employee.persona.allowed_repositories,
        prod_access=employee.persona.prod_access,
        work_hours=employee.persona.work_hours,
        daily_budget_usd=employee.persona.daily_budget_usd,
        spend_today_usd=float(counters.get("cost_usd", 0.0)),
        risk_score=int(risk.body.get("score", 0)) if risk else 0,
        sessions_today=int(counters.get("requests", 0)),
        is_low_confidence=(str(risk.body.get("confidence", "low")) if risk else "low") == "low",
    )


def _sim_date(services: Services) -> str:
    from agentshield.sim.clock import SimClock

    clock = services.container.clock
    if isinstance(clock, SimClock):
        return clock.sim_date
    from datetime import UTC, datetime

    return datetime.fromtimestamp(clock.sim_ts, tz=UTC).strftime("%Y-%m-%d")
