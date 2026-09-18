"""The agent tool-use loop.

Every tool call the model attempts re-enters Gate 2 before the sandbox sees
it. The loop caps at `LLM_MAX_ITERATIONS` and terminates rather than running
away.

The single most important behaviour in this file: **a block is returned to the
model as a tool result, never raised as an exception.** The model sees

    {"error": "blocked_by_policy", "reason": "...", "policy": "..."}

and continues -- usually by trying something else. That reaction is itself
telemetry, and it is the richest adversarial signal the system has. An agent
that adapts after one refusal looks nothing like an agent that tries the same
secret path five ways in four minutes, and an exception would erase the
difference.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import ulid

from agentshield.agent import prompts
from agentshield.agent.router import cost_of
from agentshield.agent.tools import TOOL_SCHEMAS, coerce_tool
from agentshield.domain.enums import ApprovalStatus, Decision, Environment, TaskStatus, ToolName
from agentshield.domain.models import (
    ActionContext,
    ActorContext,
    AgentAction,
    Approval,
    Task,
    digest_args,
)
from agentshield.governance.approvals import ApprovalEngine, was_approved
from agentshield.governance.gate2 import Gate2, resolve_resource
from agentshield.ports.clock import ClockPort
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.ports.llm import LLMPort
from agentshield.sandbox.executor import ExecutionContext, Sandbox
from agentshield.sim.seed_data import protected_branches
from agentshield.telemetry.emitter import TelemetryEmitter

logger = logging.getLogger(__name__)

# Identical `args_digest` inside this window counts toward the retry-loop
# guard. Five simulated minutes -- long enough to catch a loop, short enough
# that legitimate repetition across a session does not trip it.
REPEAT_WINDOW_SIM_SECONDS = 300


@dataclass
class RunnerDeps:
    llm: LLMPort
    gate2: Gate2
    sandbox: Sandbox
    approvals: ApprovalEngine
    emitter: TelemetryEmitter
    docstore: DocStorePort
    clock: ClockPort
    max_iterations: int = 8
    retry_threshold: int = 3


@dataclass
class _Session:
    """Per-task state that never leaves the loop."""

    recent_digests: list[tuple[str, int]] = field(default_factory=list)
    action_seq: int = 0

    def repeat_count(self, digest: str, now: int) -> int:
        self.recent_digests = [
            (d, ts) for d, ts in self.recent_digests if now - ts <= REPEAT_WINDOW_SIM_SECONDS
        ]
        return sum(1 for d, _ in self.recent_digests if d == digest)

    def record(self, digest: str, now: int) -> None:
        self.recent_digests.append((digest, now))


class AgentRunner:
    def __init__(self, deps: RunnerDeps) -> None:
        self._d = deps

    async def run(self, task: Task, actor: ActorContext) -> Task:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.SYSTEM_PROMPT},
            {"role": "user", "content": prompts.build_prompt(task)},
        ]
        session = _Session()
        correction_used = False

        for iteration in range(self._d.max_iterations):
            result = await self._d.llm.complete(
                messages=messages,
                tools=TOOL_SCHEMAS,
                model=task.complexity,
            )

            call_cost = cost_of(
                result.model_id, result.usage.input_tokens, result.usage.output_tokens
            )
            task.tokens_in += result.usage.input_tokens
            task.tokens_out += result.usage.output_tokens
            task.cost_usd += call_cost
            task.routed_model = result.model_id

            await self._d.emitter.emit(
                "model.invoked",
                run_id=task.run_id,
                employee_id=task.employee_id,
                task_id=task.id,
                payload={
                    "task_id": task.id,
                    "model_id": result.model_id,
                    "input_tokens": result.usage.input_tokens,
                    "output_tokens": result.usage.output_tokens,
                    "cost_usd": call_cost,
                    "iteration": iteration,
                    "stop_reason": result.stop_reason,
                    "fallback": result.fallback,
                },
            )

            if not result.tool_calls:
                return await self._complete(task, result.text)

            for call in result.tool_calls:
                tool = coerce_tool(call.name)

                if tool is None:
                    messages.append(prompts.assistant_tool_use(call, result.text))
                    messages.append(
                        prompts.tool_result_message(
                            call.id, call.name, prompts.unknown_tool_result(call.name)
                        )
                    )
                    continue

                if not isinstance(call.arguments, dict):
                    # One correction round-trip, then the session fails.
                    if correction_used:
                        return await self._fail(task, "malformed_tool_call")
                    correction_used = True
                    messages.append(prompts.assistant_tool_use(call, result.text))
                    messages.append(
                        prompts.tool_result_message(
                            call.id,
                            call.name,
                            prompts.malformed_call_result(call.name, "arguments must be an object"),
                        )
                    )
                    continue

                payload = await self._handle_tool_call(
                    task=task,
                    actor=actor,
                    tool=tool,
                    call_id=call.id,
                    args=call.arguments,
                    iteration=iteration,
                    session=session,
                )

                messages.append(prompts.assistant_tool_use(call, result.text))
                messages.append(prompts.tool_result_message(call.id, call.name, payload))

                if task.status in (TaskStatus.DENIED, TaskStatus.DENIED_TIMEOUT):
                    return await self._finish(task)

        return await self._fail(task, "max_iterations")

    # ── one governed tool call ───────────────────────────────────────

    async def _handle_tool_call(
        self,
        *,
        task: Task,
        actor: ActorContext,
        tool: ToolName,
        call_id: str,
        args: dict[str, Any],
        iteration: int,
        session: _Session,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        now = self._d.clock.sim_ts
        session.action_seq += 1

        context = self._build_action_context(
            task=task,
            actor=actor,
            tool=tool,
            args=args,
            iteration=iteration,
            session=session,
            now=now,
        )
        session.record(context.args_digest, now)

        action_id = f"act_{ulid.new()}"
        await self._d.emitter.emit(
            "action.requested",
            run_id=task.run_id,
            employee_id=task.employee_id,
            task_id=task.id,
            payload={
                "task_id": task.id,
                "action_id": action_id,
                "tool": str(tool),
                "target_resource": context.target_resource,
                "environment": str(context.environment),
                "resource_sensitivity": str(context.resource_sensitivity),
                "args_digest": context.args_digest,
                "iteration": iteration,
            },
        )

        # A session grant skips the gate entirely: an approver already saw
        # this exact tool+resource+environment tuple and said yes for the rest
        # of this task. Re-asking would be noise, and the operator would learn
        # to click through it.
        if context.grant_key in task.session_grants:
            decision_result = None
        else:
            decision_result = await self._d.gate2.evaluate(context)

        task.actions_total += 1

        if decision_result is not None:
            await self._emit_gate2(task, action_id, context, decision_result)

            if decision_result.decision is Decision.BLOCK:
                task.actions_blocked += 1
                await self._d.emitter.emit(
                    "action.blocked",
                    run_id=task.run_id,
                    employee_id=task.employee_id,
                    task_id=task.id,
                    payload={
                        "task_id": task.id,
                        "action_id": action_id,
                        "tool": str(tool),
                        "target_resource": context.target_resource,
                        "policy_id": _policy_id(decision_result.reason_code),
                        "message": decision_result.message or "blocked by policy",
                    },
                )
                await self._persist_action(
                    task, action_id, session.action_seq, context, decision_result, None, started
                )
                return prompts.blocked_result(
                    decision_result.message or "blocked by policy",
                    _policy_id(decision_result.reason_code),
                )

            if decision_result.decision is Decision.REVIEW:
                task.actions_review += 1
                outcome = await self._await_approval(task, action_id, context, decision_result)
                if outcome is not None:
                    await self._persist_action(
                        task,
                        action_id,
                        session.action_seq,
                        context,
                        decision_result,
                        None,
                        started,
                    )
                    return outcome

        # Allowed, or approved.
        result = await self._d.sandbox.execute(
            tool,
            args,
            ExecutionContext(
                task_id=task.id,
                repo=context.repo,
                environment=context.environment,
                mistake_probability=0.04,
            ),
        )

        await self._d.emitter.emit(
            "sandbox.executed",
            run_id=task.run_id,
            employee_id=task.employee_id,
            task_id=task.id,
            payload={
                "task_id": task.id,
                "action_id": action_id,
                "tool": str(tool),
                "ok": result.ok,
                "duration_ms": result.duration_ms,
                "output_preview": (result.output or result.error or "")[:200],
            },
        )
        await self._persist_action(
            task, action_id, session.action_seq, context, decision_result, result, started
        )

        return (
            {"ok": True, "output": result.output}
            if result.ok
            else {"ok": False, "error": result.error or "failed"}
        )

    # ── approval round trip ──────────────────────────────────────────

    async def _await_approval(
        self, task: Task, action_id: str, context: ActionContext, decision: Any
    ) -> dict[str, Any] | None:
        """Request approval and report the outcome.

        Returns `None` when the action may proceed, or the tool-result payload
        to hand back to the model when it may not.

        The simulator resolves approvals on its tick; a Live Mode caller polls
        `GET /approvals/{id}` or watches the WebSocket. Either way the wait is
        the caller's, not this loop's -- blocking here would stall the tick.
        """
        attributed = decision.matched_policies[0] if decision.matched_policies else None
        approval = await self._d.approvals.request(
            run_id=task.run_id,
            task=task,
            action_id=action_id,
            context=context,
            reason=decision.message or "This action needs approval.",
            policy_id=_policy_id(decision.reason_code) or "",
            approver=self._d.gate2.approver_for(attributed),
            ttl_sim_seconds=self._d.gate2.ttl_for(attributed, 300),
        )

        task.transition_to(TaskStatus.AWAITING_APPROVAL)
        resolved = await self._resolve_approval(task, approval)

        if resolved is None or resolved.status is ApprovalStatus.PENDING:
            # Still waiting. The scheduler picks the task back up once the
            # approval resolves; the loop does not spin on it.
            return prompts.expired_result()

        if was_approved(resolved.status):
            task.transition_to(TaskStatus.WORKING)
            if resolved.status is ApprovalStatus.APPROVED_SESSION:
                task.session_grants.append(context.grant_key)
            return None

        if resolved.status is ApprovalStatus.DENIED:
            task.transition_to(TaskStatus.DENIED)
            return prompts.denied_result(resolved.note or "An approver denied this action.")

        task.transition_to(TaskStatus.DENIED_TIMEOUT)
        return prompts.expired_result()

    async def _resolve_approval(self, task: Task, approval: Approval) -> Approval | None:
        try:
            return await self._d.approvals.get(task.run_id, approval.id)
        except Exception:
            logger.warning("could not re-read approval", extra={"approval_id": approval.id})
            return approval

    # ── context ──────────────────────────────────────────────────────

    def _build_action_context(
        self,
        *,
        task: Task,
        actor: ActorContext,
        tool: ToolName,
        args: dict[str, Any],
        iteration: int,
        session: _Session,
        now: int,
    ) -> ActionContext:
        resolved = resolve_resource(
            tool,
            args,
            repo=task.repo,
            environment=task.environment,
            allowed_repositories=actor.allowed_repositories,
            protected_branches=protected_branches(str(args.get("repo") or task.repo)),
        )
        digest = digest_args(tool, args)

        return ActionContext(
            source=task.source,
            actor=actor,
            task_id=task.id,
            repo=str(resolved["repo"]),
            environment=Environment(str(resolved["environment"])),
            elapsed_sim_s=max(0, now - task.started_sim_ts),
            tokens_so_far=task.tokens_in + task.tokens_out,
            cost_so_far_usd=task.cost_usd,
            actions_so_far=task.actions_total,
            blocked_so_far=task.actions_blocked,
            tool=tool,
            args=args,
            args_digest=digest,
            target_resource=str(resolved["target_resource"]),
            resource_sensitivity=resolved["resource_sensitivity"],  # type: ignore[arg-type]
            is_repo_in_scope=bool(resolved["is_repo_in_scope"]),
            is_secret_path=bool(resolved["is_secret_path"]),
            is_protected_branch=bool(resolved["is_protected_branch"]),
            is_external_host=bool(resolved["is_external_host"]),
            repeat_count_5m=session.repeat_count(digest, now),
            iteration_index=iteration,
            sim_ts=now,
        )

    # ── persistence and emission ─────────────────────────────────────

    async def _emit_gate2(
        self, task: Task, action_id: str, context: ActionContext, decision: Any
    ) -> None:
        await self._d.emitter.emit(
            "gate2.decision",
            run_id=task.run_id,
            employee_id=task.employee_id,
            task_id=task.id,
            payload={
                "task_id": task.id,
                "action_id": action_id,
                "tool": str(context.tool),
                "decision": str(decision.decision),
                "reason_code": decision.reason_code,
                "matched_policies": [m.model_dump(mode="json") for m in decision.matched_policies],
                "target_resource": context.target_resource,
                "environment": str(context.environment),
                "repeat_count_5m": context.repeat_count_5m,
                "latency_ms": decision.latency_ms,
            },
        )

    async def _persist_action(
        self,
        task: Task,
        action_id: str,
        seq: int,
        context: ActionContext,
        decision: Any,
        result: Any,
        started: float,
    ) -> None:
        action = AgentAction(
            id=action_id,
            task_id=task.id,
            run_id=task.run_id,
            seq=seq,
            tool=context.tool,
            args=context.args,
            args_digest=context.args_digest,
            target_resource=context.target_resource,
            resource_sensitivity=context.resource_sensitivity,
            environment=context.environment,
            decision=decision.decision if decision else Decision.ALLOW,
            reason_code=decision.reason_code if decision else "session_grant",
            matched_policies=decision.matched_policies if decision else [],
            result=result,
            # The full evaluated context, so the Policy Lab can replay this
            # decision without rebuilding it by join (decision D8).
            context_snapshot=context.model_dump(mode="json"),
            latency_ms=(time.perf_counter() - started) * 1000.0,
            sim_ts=context.sim_ts,
        )
        await self._d.docstore.put(
            DocItem(
                pk=f"TASK#{task.id}",
                sk=f"ACT#{seq:04d}",
                gsi1pk=f"RUN#{task.run_id}#TOOL#{context.tool}",
                gsi1sk=f"{context.sim_ts:010d}",
                body=action.model_dump(mode="json"),
            )
        )

    # ── termination ──────────────────────────────────────────────────

    async def _complete(self, task: Task, summary: str) -> Task:
        task.transition_to(TaskStatus.COMPLETED)
        return await self._finish(task, summary)

    async def _fail(self, task: Task, reason: str) -> Task:
        task.transition_to(TaskStatus.FAILED)
        return await self._finish(task, reason)

    async def _finish(self, task: Task, summary: str = "") -> Task:
        task.ended_sim_ts = self._d.clock.sim_ts
        await self._d.emitter.emit(
            "task.completed",
            run_id=task.run_id,
            employee_id=task.employee_id,
            task_id=task.id,
            payload={
                "task_id": task.id,
                "employee_id": task.employee_id,
                "status": str(task.status),
                "tokens_in": task.tokens_in,
                "tokens_out": task.tokens_out,
                "cost_usd": task.cost_usd,
                "actions_total": task.actions_total,
                "actions_blocked": task.actions_blocked,
                "duration_sim_s": max(0, (task.ended_sim_ts or 0) - task.started_sim_ts),
            },
        )
        await self._d.docstore.put(
            DocItem(pk=f"TASK#{task.id}", sk="META", body=task.model_dump(mode="json"))
        )
        return task


def _policy_id(reason_code: str) -> str | None:
    return reason_code.split(":", 1)[1] if reason_code.startswith("policy:") else None
