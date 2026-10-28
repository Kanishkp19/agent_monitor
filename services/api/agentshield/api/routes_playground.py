"""The Sandbox playground: try the gates with no sign-in.

One route file, one promise: **the exact same governance path as everything
else.** A visitor picks a role, types a prompt, picks a model, and watches
Gate 1 / Gate 2 decisions stream back with the reasons and policy ids -- the
same `gate1.evaluate()` / `gate2.evaluate()` calls the simulation and Live
Mode make. Nothing here is a second implementation of the rules.

**Why bearer `demo-<role>` and no sign-in.** The playground's purpose is to
let a stranger feel the rulebook in one minute. But identity must still come
from the *credential*, never the body (the Live Mode property, preserved):
`demo-intern` means the intern actor, whatever the request claims. Roles map
to real seeded employees' personas -- an intern playground session is
governed exactly like emp_013 would be. The token prefix is recognised
separately from `INGEST_TOKENS`, is rate-limited like any other caller, and
grants nothing beyond that role's own authority. To add a role, seed an
employee; to change what a role may do, change policies -- the same two
answers as everywhere else in the product.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Any

import ulid
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from agentshield.agent.router import cost_of, estimate_tokens, route
from agentshield.agent.tools import TOOL_SCHEMAS, coerce_tool
from agentshield.api.schemas import ok
from agentshield.deps import Services, get_services
from agentshield.domain.enums import Decision, Environment, Source, TaskStatus
from agentshield.domain.errors import (
    NotFound,
    RateLimited,
    Unauthorized,
    ValidationFailed,
)
from agentshield.domain.models import (
    ActionContext,
    ActorContext,
    RequestContext,
    Task,
    digest_args,
)
from agentshield.governance.gate2 import resolve_resource
from agentshield.governance.redaction import raw_prompt_key
from agentshield.ports.docstore import DocItem
from agentshield.sandbox.executor import ExecutionContext
from agentshield.sim.clock import SimClock
from agentshield.sim.seed_data import protected_branches

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playground", tags=["playground"])

# Per-identity request rate limit. The playground is unauthenticated, so the
# limiter is what stops it from becoming a free Gate-1 CPU farm; the ceiling
# is far above human interaction and far below what could perturb a demo.
_RATE_LIMIT = 30
_RATE_WINDOW_SECONDS = 10.0
_requests: dict[str, deque[float]] = defaultdict(deque)

# The role menu. Personas come from real seeded employees when one with the
# role exists, so the governance a visitor experiences is the governance the
# office enforces.
ROLE_CATALOG: dict[str, dict[str, Any]] = {
    "engineering_intern": {"model": "trivial", "prod_access": False, "experience": "low"},
    "engineer": {"model": "standard", "prod_access": False, "experience": "medium"},
    "senior_engineer": {"model": "standard", "prod_access": False, "experience": "high"},
    "manager": {"model": "complex", "prod_access": True, "experience": "high"},
    "devops": {"model": "complex", "prod_access": True, "experience": "high"},
}

REPO_MENU = ["payments-api", "payments-web", "platform-core", "infra-terraform", "data-pipeline"]
ENV_MENU = ["local", "staging", "production"]
TASK_TYPES = [
    "bug_fix",
    "unit_test",
    "documentation",
    "api_work",
    "data_access",
    "deployment",
    "refactor",
    "incident_response",
]

MODEL_CATALOG: dict[str, dict[str, str]] = {
    "auto": {"label": "Auto (policy router decides)", "complexity": ""},
    "trivial": {"label": "Trivial tier", "complexity": "trivial"},
    "standard": {"label": "Standard tier", "complexity": "standard"},
    "complex": {"label": "Complex / frontier tier", "complexity": "complex"},
}


class PlaygroundGate1Request(BaseModel):
    role: str
    task_type: str = "bug_fix"
    complexity: str = "standard"
    repo: str = "payments-api"
    environment: str = "local"
    prompt: str = Field(min_length=1, max_length=100_000)
    requested_model: str | None = None


class PlaygroundTaskRequest(BaseModel):
    role: str
    title: str = "Playground task"
    repo: str = "payments-api"
    environment: str = "local"
    task_type: str = "bug_fix"
    complexity: str = "standard"


class PlaygroundActionRequest(BaseModel):
    role: str
    task_id: str
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0


def _identity(authorization: str) -> tuple[str, str]:
    """`Bearer demo-<role>` -> (role, actor_id).

    Identity comes from the credential, never the body. An unknown role is a
    401 -- the caller may not invent personas.
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("demo-"):
        raise Unauthorized("Use `Authorization: Bearer demo-<role>` with a playground role.")
    role = token.removeprefix("demo-").strip()
    if role not in ROLE_CATALOG:
        raise Unauthorized(
            f"unknown playground role {role!r}", details={"roles": sorted(ROLE_CATALOG)}
        )
    return role, f"emp_P{role}"


def _enforce_rate_limit(identity: str) -> None:
    now = time.monotonic()
    window = _requests[identity]
    while window and now - window[0] > _RATE_WINDOW_SECONDS:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        raise RateLimited(f"Over {_RATE_LIMIT} playground requests per {_RATE_WINDOW_SECONDS:g}s.")
    window.append(now)


def _sim_date(services: Services) -> str:
    clock = services.container.clock
    if isinstance(clock, SimClock):
        return clock.sim_date
    from datetime import UTC, datetime

    return datetime.fromtimestamp(clock.sim_ts, tz=UTC).strftime("%Y-%m-%d")


async def _active_run_id(services: Services) -> str:
    """The most recent run -- the one the office and Live Feed already show."""
    runs = await services.seeder.recent_runs(limit=1)
    if not runs:
        raise NotFound("no runs exist yet -- seed one with `python tasks.py seed`")
    return runs[0].id


async def _actor_for(services: Services, run_id: str, role: str, actor_id: str) -> ActorContext:
    """Build the actor from the seeded persona of a matching employee.

    If a real employee with that role exists, their exact persona is used.
    Otherwise one is synthesised from the role catalog. Either way, nothing
    comes from the request body.
    """
    spec = ROLE_CATALOG[role]
    employee = None
    for candidate in await services.seeder.load_employees(run_id):
        if candidate.role.value == role:
            employee = candidate
            break

    if employee is not None:
        persona = employee.persona
        return ActorContext(
            id=actor_id,
            role=employee.role,
            team=employee.team,
            seniority=persona.experience,
            allowed_repositories=persona.allowed_repositories,
            prod_access=persona.prod_access,
            work_hours=persona.work_hours,
            # A generous floor so a demo session does not trip budget guards
            # that exist for cumulative *simulated* employees.
            daily_budget_usd=max(persona.daily_budget_usd, 25.0),
            spend_today_usd=0.0,
            risk_score=0,
            sessions_today=0,
            is_low_confidence=False,
        )

    return ActorContext(
        id=actor_id,
        role=role,  # type: ignore[arg-type]
        team="payments",
        seniority=spec["experience"],
        allowed_repositories=list(REPO_MENU),
        prod_access=bool(spec["prod_access"]),
        work_hours=(8, 20),
        daily_budget_usd=50.0,
        spend_today_usd=0.0,
        risk_score=0,
        sessions_today=0,
        is_low_confidence=False,
    )


async def _load_task(services: Services, run_id: str, task_id: str) -> Task:
    item = await services.container.docstore.get(f"TASK#{task_id}", "META")
    if item is None:
        raise NotFound(f"no task {task_id!r}")
    task = Task.model_validate(item.body)
    if task.run_id != run_id:
        raise NotFound(f"task {task_id!r} belongs to another run")
    return task


# ──────────────────────────────────────────────────────────────────────
# Context for the UI


@router.get("/context")
async def playground_context(services: Services = Depends(get_services)) -> dict[str, Any]:
    return ok(
        {
            "roles": [
                {"id": role, "label": role.replace("_", " ").title(), **spec}
                for role, spec in sorted(ROLE_CATALOG.items())
            ],
            "models": [
                {"id": model_id, "label": spec["label"]} for model_id, spec in MODEL_CATALOG.items()
            ],
            "repos": REPO_MENU,
            "environments": ENV_MENU,
            "task_types": TASK_TYPES,
            "tools": [
                {"name": schema.get("name", ""), "description": schema.get("description", "")}
                for schema in TOOL_SCHEMAS
            ],
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Task bootstrap


@router.post("/tasks/create")
async def playground_create_task(
    body: PlaygroundTaskRequest,
    services: Services = Depends(get_services),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    role, actor_id = _identity(authorization)
    _enforce_rate_limit(f"{role}:create")
    run_id = await _active_run_id(services)
    await _actor_for(services, run_id, role, actor_id)

    task = Task(
        id=f"task_{ulid.new().str[-8:].lower()}",
        run_id=run_id,
        employee_id=actor_id,
        title=body.title,
        task_type=body.task_type,  # type: ignore[arg-type]
        complexity=body.complexity,  # type: ignore[arg-type]
        repo=body.repo,
        environment=Environment(body.environment),
        status=TaskStatus.WORKING,
        started_sim_ts=services.container.clock.sim_ts,
        prompt_text=body.title,
        source=Source.LIVE,
    )
    await services.container.docstore.put(
        DocItem(pk=f"TASK#{task.id}", sk="META", body=task.model_dump(mode="json"))
    )
    return ok({"task_id": task.id, "status": str(task.status), "run_id": run_id})


# ──────────────────────────────────────────────────────────────────────
# Gate 1 -- the request decision


@router.post("/gate1")
async def playground_gate1(
    body: PlaygroundGate1Request,
    services: Services = Depends(get_services),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    role, actor_id = _identity(authorization)
    _enforce_rate_limit(f"{role}:gate1")
    run_id = await _active_run_id(services)

    actor = await _actor_for(services, run_id, role, actor_id)
    settings = services.container.settings

    complexity = (
        body.complexity if body.complexity in ("trivial", "standard", "complex") else "standard"
    )
    if body.requested_model and body.requested_model in MODEL_CATALOG:
        chosen = MODEL_CATALOG[body.requested_model]["complexity"]
        if chosen:
            complexity = chosen

    est_in, est_out = estimate_tokens(body.task_type, complexity, len(body.prompt))
    routed = route(complexity, provider=settings.llm_provider, requested=None)

    task = Task(
        id=f"task_{ulid.new().str[-8:].lower()}",
        run_id=run_id,
        employee_id=actor_id,
        title=body.prompt[:80],
        task_type=body.task_type,  # type: ignore[arg-type]
        complexity=complexity,
        repo=body.repo,
        environment=Environment(body.environment),
        status=TaskStatus.REQUESTING,
        started_sim_ts=services.container.clock.sim_ts,
        prompt_text=body.prompt,
        source=Source.LIVE,
    )

    context = RequestContext(
        source=Source.LIVE,
        actor=actor,
        task_id=task.id,
        task_type=task.task_type,
        complexity=complexity,
        repo=body.repo,
        environment=task.environment,
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

    # THE identical call the office and Live Mode make.
    result = await services.gate1.evaluate(context, run_id=run_id, sim_date=_sim_date(services))

    prompt_out = body.prompt
    if result.redacted_text is not None:
        prompt_out = result.redacted_text
        await services.container.blobs.put_object(
            raw_prompt_key(task.id), body.prompt.encode(), "application/json"
        )

    await services.container.docstore.put(
        DocItem(pk=f"TASK#{task.id}", sk="META", body=task.model_dump(mode="json"))
    )
    await services.emitter.emit(
        "gate1.decision",
        run_id=run_id,
        employee_id=actor_id,
        task_id=task.id,
        payload={
            "task_id": task.id,
            "decision": str(result.decision),
            "reason_code": result.reason_code,
            "matched_policies": [m.model_dump(mode="json") for m in result.matched_policies],
            "routed_model": routed,
            "est_cost_usd": context.est_cost_usd,
            "latency_ms": result.latency_ms,
            "source": "playground",
        },
    )

    return ok(
        {
            "decision": str(result.decision),
            "reason": result.message or result.reason_code,
            "reason_code": result.reason_code,
            "policy_ids": [m.policy_id for m in result.matched_policies],
            "matched_policies": [m.model_dump(mode="json") for m in result.matched_policies],
            "routed_model": routed,
            "est_cost_usd": round(context.est_cost_usd, 6),
            "prompt": prompt_out,
            "redacted": result.redacted_text is not None,
            "approval_id": result.approval_id,
            "task_id": task.id,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Gate 2 -- the action decision


@router.post("/gate2")
async def playground_gate2(
    body: PlaygroundActionRequest,
    services: Services = Depends(get_services),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    role, actor_id = _identity(authorization)
    _enforce_rate_limit(f"{role}:gate2")
    run_id = await _active_run_id(services)

    task = await _load_task(services, run_id, body.task_id)
    actor = await _actor_for(services, run_id, role, actor_id)

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
        tool=body.tool,  # type: ignore[arg-type]
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

    task.actions_total += 1
    if result.decision is Decision.BLOCK:
        task.actions_blocked += 1
    await services.container.docstore.put(
        DocItem(pk=f"TASK#{task.id}", sk="META", body=task.model_dump(mode="json"))
    )

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
            "source": "playground",
        },
    )

    return ok(
        {
            "decision": str(result.decision),
            "reason": result.message or result.reason_code,
            "reason_code": result.reason_code,
            "policy_ids": [m.policy_id for m in result.matched_policies],
            "matched_policies": [m.model_dump(mode="json") for m in result.matched_policies],
            "target_resource": context.target_resource,
            "approval_id": approval_id,
            "action_id": action_id,
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Universal agent hook -- the one URL any coding tool can call


class AgentHookRequest(BaseModel):
    """One envelope for every integration style.

    `prompt` present -> Gate 1 (pre-flight, before a model call).
    `tool` present   -> Gate 2 (before a tool executes; the sandbox runs it
    when allowed, so the caller gets the simulated outcome in one round trip).
    `mode=demo` governs as the named role (no sign-in -- the Sandbox page and
    configured agents). `mode=live` requires a real `INGEST_TOKENS` bearer
    and resolves identity server-side, exactly like `/ingest/*`.
    """

    mode: str = "demo"
    role: str = "engineering_intern"
    task: str = "Agent task"
    task_type: str = "bug_fix"
    complexity: str = "standard"
    repo: str = "payments-api"
    environment: str = "local"
    prompt: str | None = None
    requested_model: str | None = None
    tool: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    iteration: int = 0
    task_id: str | None = None


@router.post("/hook/agent")
async def agent_hook(
    body: AgentHookRequest,
    services: Services = Depends(get_services),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """The integration point for Claude Code hooks, Codex, MCP clients.

    Decision only -- never raises for a governed refusal. A caller that gets
    `{decision: "block"}` must not proceed; `{decision: "allow"}` plus
    `result` means the sandbox already executed it.
    """
    if body.mode == "live":
        return await _hook_live(body, services, authorization)
    return await _hook_demo(body, services)


async def _hook_demo(body: AgentHookRequest, services: Services) -> dict[str, Any]:
    if body.prompt is not None:
        gate1 = await playground_gate1(
            PlaygroundGate1Request(
                role=body.role,
                task_type=body.task_type,
                complexity=body.complexity,
                repo=body.repo,
                environment=body.environment,
                prompt=body.prompt,
                requested_model=body.requested_model,
            ),
            services=services,
            authorization=f"Bearer demo-{body.role}",
        )
        return gate1

    if body.tool is None:
        raise ValidationFailed("provide either `prompt` (gate 1) or `tool` (gate 2)")

    task_id = body.task_id
    if task_id is None:
        created = await playground_create_task(
            PlaygroundTaskRequest(
                role=body.role,
                title=body.task,
                repo=body.repo,
                environment=body.environment,
                task_type=body.task_type,
                complexity=body.complexity,
            ),
            services=services,
            authorization=f"Bearer demo-{body.role}",
        )
        task_id = str(created["data"]["task_id"])

    return await playground_tool(
        PlaygroundActionRequest(
            role=body.role,
            task_id=task_id,
            tool=body.tool,
            args=body.args,
            iteration=body.iteration,
        ),
        services=services,
        authorization=f"Bearer demo-{body.role}",
    )


async def _hook_live(
    body: AgentHookRequest, services: Services, authorization: str
) -> dict[str, Any]:
    """Live Mode through the hook: identity from the bearer, never the body."""
    from agentshield.api.routes_ingest import authenticate

    actor_id = await authenticate(authorization, services)
    runs = await services.seeder.recent_runs(limit=1)
    if not runs:
        raise NotFound("no runs exist yet")
    run_id = runs[0].id

    if body.prompt is not None:
        from agentshield.api.routes_ingest import ingest_gate1
        from agentshield.api.schemas import IngestGate1Request

        return await ingest_gate1(
            IngestGate1Request(
                task_ref=body.task,
                task_type=body.task_type,
                complexity=body.complexity,  # type: ignore[arg-type]
                repo=body.repo,
                environment=body.environment,
                prompt=body.prompt,
                requested_model=body.requested_model,
            ),
            run_id=run_id,
            actor_id=actor_id,
            services=services,
        )

    if body.tool is None:
        raise ValidationFailed("provide either `prompt` (gate 1) or `tool` (gate 2)")

    task_id = body.task_id
    if task_id is None:
        raise ValidationFailed("live mode requires the task_id returned by your gate1 call")

    from agentshield.api.routes_ingest import ingest_gate2
    from agentshield.api.schemas import IngestGate2Request

    return await ingest_gate2(
        IngestGate2Request(
            task_id=task_id,
            tool=body.tool,  # type: ignore[arg-type]
            args=body.args,
            iteration=body.iteration,
        ),
        run_id=run_id,
        actor_id=actor_id,
        services=services,
    )


# ──────────────────────────────────────────────────────────────────────
# Tool execution -- governance + the simulated sandbox in one call


@router.post("/tool")
async def playground_tool(
    body: PlaygroundActionRequest,
    services: Services = Depends(get_services),
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Gate 2, then the sandbox: what a real agent experiences per tool call."""
    role, _actor_id = _identity(authorization)
    _enforce_rate_limit(f"{role}:tool")

    if coerce_tool(body.tool) is None:
        raise NotFound(
            f"unknown tool {body.tool!r}",
            details={"known": [s.get("name") for s in TOOL_SCHEMAS]},
        )

    gate = await playground_gate2(body, services=services, authorization=authorization)
    gate_data = gate["data"]

    if gate_data["decision"] != "allow":
        # A block is a tool result, not an exception -- the agent's reaction
        # to a refusal is the richest telemetry there is (invariant 12). The
        # playground keeps that contract.
        return ok(
            {
                **gate_data,
                "executed": False,
                "result": {"error": "blocked_by_policy", "reason": gate_data["reason"]},
            }
        )

    run_id = await _active_run_id(services)
    task = await _load_task(services, run_id, body.task_id)
    execution = await services.sandbox.execute(
        coerce_tool(body.tool),  # type: ignore[arg-type]
        body.args,
        ExecutionContext(
            task_id=task.id,
            repo=task.repo,
            environment=task.environment,
            mistake_probability=0.04,
        ),
    )

    await services.emitter.emit(
        "sandbox.executed",
        run_id=run_id,
        employee_id=task.employee_id,
        task_id=task.id,
        payload={
            "task_id": task.id,
            "tool": str(body.tool),
            "ok": execution.ok,
            "duration_ms": execution.duration_ms,
            "source": "playground",
        },
    )

    return ok(
        {
            **gate_data,
            "executed": True,
            "result": {
                "ok": execution.ok,
                "output": execution.output,
                "error": execution.error,
                "duration_ms": execution.duration_ms,
            },
        }
    )
