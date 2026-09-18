"""The simulation engine: tick loop, speed control, concurrency cap.

Twenty employees, at most four concurrent agent sessions, one tick per
simulated minute. Behaviour volume is separated from behaviour fidelity: the
twenty are cheap state machines, and only the marquee sessions invoke a real
model.

Three rules this file is responsible for:

**`advance()` forces MockLLM.** Regardless of `LLM_PROVIDER`. A fast-forward
that calls a real model takes minutes instead of seconds and produces a
different event stream every run -- the documented cause of both symptoms.

**The TTL sweep runs on `clock.sim_ts`.** Never wall time. During a 100x
fast-forward wall time barely moves while days pass, and approvals would
never expire.

**Ticks never queue.** If a tick overruns its wall-clock budget the engine
drops to the next lower speed and says so. Letting ticks pile up turns a
smooth 10x into a stuttering one that is slower than 1x.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agentshield.agent.router import estimate_tokens, route
from agentshield.agent.runner import AgentRunner
from agentshield.domain.enums import (
    Decision,
    SimSpeed,
    TaskStatus,
)
from agentshield.domain.models import (
    ActorContext,
    Employee,
    GateRequest,
    RequestContext,
    SimRun,
    Task,
)
from agentshield.governance.gate1 import Gate1
from agentshield.governance.redaction import raw_prompt_key, to_event_findings
from agentshield.ports.blobstore import BlobStorePort
from agentshield.ports.clock import ClockPort
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.ports.llm import LLMPort
from agentshield.sim.clock import SimClock
from agentshield.sim.scenarios import ScenarioEngine
from agentshield.sim.seed import Seeder
from agentshield.sim.task_generator import TaskGenerator
from agentshield.telemetry.counters import WASTE_STATUSES, Counters
from agentshield.telemetry.emitter import TelemetryEmitter

logger = logging.getLogger(__name__)

TICK_SIM_SECONDS = 60

# Wall-clock interval per tick, by speed. 100x does not tick on a timer at
# all -- it runs a headless batch loop with a progress frame every 250 ms.
TICK_INTERVAL_MS: dict[SimSpeed, int] = {
    SimSpeed.REALTIME: 1000,
    SimSpeed.FAST: 100,
    SimSpeed.TURBO: 0,
}

# A tick that takes longer than this fraction of its interval is overrunning.
OVERRUN_RATIO = 0.9


@dataclass
class EngineDeps:
    docstore: DocStorePort
    blobs: BlobStorePort
    clock: ClockPort
    emitter: TelemetryEmitter
    counters: Counters
    gate1: Gate1
    runner: AgentRunner
    seeder: Seeder
    generator: TaskGenerator
    scenarios: ScenarioEngine
    max_concurrent: int = 4
    llm_provider: str = "mock"
    deterministic_llm_factory: Callable[[], LLMPort] | None = None
    """Produces a fresh, seeded MockLLMAdapter for `advance()` to force.

    Supplied by `deps.py` from `container.deterministic_llm` -- `sim/` may not
    import `adapters/` directly, so this factory is the sanctioned door.
    """


@dataclass
class RunState:
    run: SimRun
    employees: dict[str, Employee] = field(default_factory=dict)
    active: dict[str, Task] = field(default_factory=dict)
    queued: list[Task] = field(default_factory=list)
    day_stats: dict[str, Any] = field(default_factory=dict)
    paused: bool = False
    busy: bool = False
    """True during a 100x batch. Control actions other than `pause` return 409
    while this is set -- changing speed mid-batch would corrupt the frame
    sequence the client is reconciling against.
    """


class SimulationEngine:
    def __init__(self, deps: EngineDeps) -> None:
        self._d = deps
        self._runs: dict[str, RunState] = {}
        self._task: asyncio.Task[None] | None = None
        self._on_downshift: Callable[[str, SimSpeed], None] | None = None

    # ── lifecycle ────────────────────────────────────────────────────

    async def attach(self, run: SimRun) -> RunState:
        employees = await self._d.seeder.load_employees(run.id)
        state = RunState(run=run, employees={e.id: e for e in employees})
        self._runs[run.id] = state
        return state

    def state(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def on_downshift(self, callback: Callable[[str, SimSpeed], None]) -> None:
        self._on_downshift = callback

    async def start(self, run_id: str) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        state.paused = False
        state.run.status = "running"
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(run_id))

    async def pause(self, run_id: str) -> None:
        state = self._runs.get(run_id)
        if state:
            state.paused = True
            state.run.status = "paused"

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    def set_speed(self, run_id: str, speed: SimSpeed) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        state.run.speed = int(speed)
        if isinstance(self._d.clock, SimClock):
            self._d.clock.set_speed(speed)

    # ── the loop ─────────────────────────────────────────────────────

    async def _loop(self, run_id: str) -> None:
        """One tick per simulated minute, paced by the current speed."""
        while True:
            state = self._runs.get(run_id)
            if state is None:
                return
            if state.paused:
                await asyncio.sleep(0.2)
                continue

            speed = SimSpeed(state.run.speed)
            if speed is SimSpeed.PAUSED:
                await asyncio.sleep(0.2)
                continue

            interval_ms = TICK_INTERVAL_MS.get(speed, 1000)
            started = time.perf_counter()

            try:
                await self.tick(run_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick failed", extra={"run_id": run_id})

            elapsed_ms = (time.perf_counter() - started) * 1000.0

            if interval_ms and elapsed_ms > interval_ms * OVERRUN_RATIO:
                self._downshift(state, speed)
                interval_ms = TICK_INTERVAL_MS.get(SimSpeed(state.run.speed), 1000)

            remaining = max(0.0, (interval_ms - elapsed_ms) / 1000.0)
            await asyncio.sleep(remaining)

    def _downshift(self, state: RunState, current: SimSpeed) -> None:
        """Drop a gear rather than let ticks queue."""
        lower = {SimSpeed.TURBO: SimSpeed.FAST, SimSpeed.FAST: SimSpeed.REALTIME}.get(current)
        if lower is None:
            return
        logger.warning(
            "tick overran; dropping speed",
            extra={"run_id": state.run.id, "from": current.name, "to": lower.name},
        )
        state.run.speed = int(lower)
        if self._on_downshift:
            self._on_downshift(state.run.id, lower)

    # ── one tick ─────────────────────────────────────────────────────

    async def tick(self, run_id: str) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return

        clock = self._d.clock
        previous_day = _sim_day(clock, state)
        clock.advance(TICK_SIM_SECONDS)
        state.run.sim_ts = clock.sim_ts

        # Expiry first: an approval that timed out during this minute frees
        # its task before the scheduler looks for work.
        await self._d.runner._d.approvals.sweep_expired(run_id)

        sim_day = _sim_day(clock, state)
        hour = _sim_hour(clock)

        await self._generate_tasks(state, sim_day, hour)
        await self._drain_queue(state)

        await self._d.emitter.emit(
            "sim.tick",
            run_id=run_id,
            payload={
                "sim_ts": clock.sim_ts,
                "active_sessions": len(state.active),
                "queued_tasks": len(state.queued),
            },
        )

        if sim_day > previous_day:
            await self._close_day(state, previous_day)

    async def _generate_tasks(self, state: RunState, sim_day: int, hour: int) -> None:
        for employee in _stable_order(state.employees):
            if employee.id in state.active:
                continue
            if not self._d.generator.should_start(employee, sim_day, hour):
                continue
            generated = self._d.generator.generate(employee, sim_day, hour, self._d.clock.sim_ts)
            state.queued.append(generated.task)

    async def _drain_queue(self, state: RunState) -> None:
        """Start sessions up to the concurrency cap. The rest wait."""
        while state.queued and len(state.active) < self._d.max_concurrent:
            task = state.queued.pop(0)
            employee = state.employees.get(task.employee_id)
            if employee is None:
                continue
            state.active[employee.id] = task
            session_task = asyncio.create_task(self._run_session(state, employee, task))
            # Referenced so it is not garbage-collected mid-flight, and so a
            # session's own exception surfaces instead of vanishing silently.
            session_task.add_done_callback(_log_session_result)

    # ── one session ──────────────────────────────────────────────────

    async def _run_session(self, state: RunState, employee: Employee, task: Task) -> None:
        run_id = state.run.id
        try:
            await self._d.emitter.emit(
                "task.requested",
                run_id=run_id,
                employee_id=employee.id,
                task_id=task.id,
                payload={
                    "task_id": task.id,
                    "employee_id": employee.id,
                    "title": task.title,
                    "task_type": task.task_type,
                    "complexity": task.complexity,
                    "repo": task.repo,
                    "environment": str(task.environment),
                    "is_marquee": task.is_marquee,
                },
            )

            actor = await self._build_actor(state, employee)
            decision = await self._run_gate1(state, employee, task, actor)

            if decision is Decision.BLOCK:
                task.transition_to(TaskStatus.REQUESTING)
                task.transition_to(TaskStatus.BLOCKED)
                await self._finalise(state, task)
                return

            task.transition_to(TaskStatus.REQUESTING)
            task.transition_to(TaskStatus.WORKING)
            await self._d.runner.run(task, actor)
            await self._finalise(state, task)

        except Exception:
            logger.exception("session failed", extra={"task_id": task.id})
        finally:
            state.active.pop(employee.id, None)

    async def _run_gate1(
        self, state: RunState, employee: Employee, task: Task, actor: ActorContext
    ) -> Decision:
        clock = self._d.clock
        sim_date = _sim_date(clock)

        est_in, est_out = estimate_tokens(task.task_type, task.complexity, len(task.prompt_text))
        routed = route(
            task.complexity,
            provider=self._d.llm_provider,
            requested=None,
        )
        from agentshield.agent.router import cost_of  # local: avoids a cycle at import time

        context = RequestContext(
            source=task.source,
            actor=actor,
            task_id=task.id,
            task_type=task.task_type,
            complexity=task.complexity,
            repo=task.repo,
            environment=task.environment,
            prompt_text=task.prompt_text,
            prompt_len=len(task.prompt_text),
            est_input_tokens=est_in,
            est_output_tokens=est_out,
            est_cost_usd=cost_of(routed, est_in, est_out),
            routed_model=routed,
            off_hours=not _in_work_hours(employee, _sim_hour(clock)),
            sim_ts=clock.sim_ts,
        )

        result = await self._d.gate1.evaluate(
            context,
            run_id=state.run.id,
            sim_date=sim_date,
            team_budget_usd=None,
        )

        # A route override from a matched policy is the "interns use cheaper
        # models" rule taking effect. Recomputing the estimate here is what
        # makes the Policy Lab's savings figure real rather than notional.
        if result.route_override:
            routed = route(
                task.complexity,
                provider=self._d.llm_provider,
                override=result.route_override,
            )
            context.routed_model = routed
            context.est_cost_usd = cost_of(routed, est_in, est_out)

        task.routed_model = routed
        task.risk_at_request = actor.risk_score

        # The raw prompt goes to the blob store and nowhere else. The event
        # below carries masked findings only.
        if result.redacted_text is not None:
            task.prompt_text = result.redacted_text
            await self._d.blobs.put_object(
                raw_prompt_key(task.id),
                context.prompt_text.encode(),
                "application/json",
            )

        request_id = f"req_{task.id}"
        await self._persist_gate1(state, task, context, result, request_id)

        await self._d.emitter.emit(
            "gate1.decision",
            run_id=state.run.id,
            employee_id=employee.id,
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

        await self._d.counters.record_decision(
            run_id=state.run.id,
            employee_id=employee.id,
            team=employee.team,
            sim_date=sim_date,
            decision=result.decision,
        )

        return result.decision

    async def _persist_gate1(
        self,
        state: RunState,
        task: Task,
        context: RequestContext,
        result: Any,
        request_id: str,
    ) -> None:
        record = GateRequest(
            id=request_id,
            task_id=task.id,
            run_id=state.run.id,
            est_input_tokens=context.est_input_tokens,
            est_output_tokens=context.est_output_tokens,
            est_cost_usd=context.est_cost_usd,
            routed_model=context.routed_model,
            findings=context.findings,
            decision=result.decision,
            reason_code=result.reason_code,
            matched_policies=result.matched_policies,
            # The full evaluated context, for replay and audit (decision D8).
            context_snapshot=context.model_dump(mode="json", exclude={"prompt_text"}),
            latency_ms=result.latency_ms,
            sim_ts=context.sim_ts,
        )
        await self._d.docstore.put(
            DocItem(
                pk=f"TASK#{task.id}",
                sk=f"REQ#{request_id}",
                body=record.model_dump(mode="json"),
            )
        )

    async def _build_actor(self, state: RunState, employee: Employee) -> ActorContext:
        sim_date = _sim_date(self._d.clock)
        counters = await self._d.counters.read(state.run.id, "emp", employee.id, sim_date)
        risk = await self._d.docstore.get(f"RUN#{state.run.id}", f"RISK#{employee.id}")
        risk_score = int(risk.body.get("score", 0)) if risk else 0
        confidence = str(risk.body.get("confidence", "low")) if risk else "low"

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
            risk_score=risk_score,
            sessions_today=int(counters.get("requests", 0)),
            is_low_confidence=confidence == "low",
        )

    async def _finalise(self, state: RunState, task: Task) -> None:
        sim_date = _sim_date(self._d.clock)
        employee = state.employees.get(task.employee_id)
        if employee is None:
            return

        await self._d.counters.record_decision(
            run_id=state.run.id,
            employee_id=employee.id,
            team=employee.team,
            sim_date=sim_date,
            decision=Decision.ALLOW,
            tokens=task.tokens_in + task.tokens_out,
            cost_usd=task.cost_usd,
        )

        if task.status in WASTE_STATUSES:
            await self._d.counters.record_waste(
                run_id=state.run.id,
                sim_date=sim_date,
                cost_usd=task.cost_usd,
                reason=str(task.status),
            )

        await self._d.docstore.put(
            DocItem(
                pk=f"RUN#{state.run.id}",
                sk=f"TASK#{task.started_sim_ts:010d}#{task.id}",
                gsi1pk=f"RUN#{state.run.id}#EMP#{task.employee_id}",
                gsi1sk=f"TASK#{task.started_sim_ts:010d}",
                gsi2pk=f"RUN#{state.run.id}#STATUS#{task.status}",
                gsi2sk=f"{task.started_sim_ts:010d}",
                body=task.model_dump(mode="json"),
            )
        )

    async def _close_day(self, state: RunState, sim_day: int) -> None:
        sim_date = _sim_date(self._d.clock)
        totals = await self._d.counters.read(state.run.id, "run", "", sim_date)
        state.run.sim_day = sim_day

        await self._d.emitter.emit(
            "sim.day.completed",
            run_id=state.run.id,
            payload={
                "sim_day": sim_day,
                "tasks": int(totals.get("requests", 0)),
                "events": await self._d.emitter.current_seq(state.run.id),
                "cost_usd": float(totals.get("cost_usd", 0.0)),
                "blocked": int(totals.get("blocked", 0)),
                "approvals": int(totals.get("review", 0)),
                "incidents": 0,
            },
        )
        await self._d.seeder.save_run(state.run)

    # ── fast-forward ─────────────────────────────────────────────────

    async def advance(
        self,
        run_id: str,
        *,
        sim_days: int | None = None,
        sim_hours: int | None = None,
        progress: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Headless fast-forward.

        Forces `MockLLM` for the duration regardless of `LLM_PROVIDER`. A real
        model here is the documented cause of a fast-forward taking minutes,
        and it would make the run non-reproducible on top of that.
        """
        state = self._runs.get(run_id)
        if state is None:
            return {}

        total_minutes = (sim_days or 0) * 24 * 60 + (sim_hours or 0) * 60
        if total_minutes <= 0:
            return {}

        started_wall = time.perf_counter()
        start_seq = await self._d.emitter.current_seq(run_id)
        start_day = _sim_day(self._d.clock, state)

        original_llm = self._d.runner._d.llm
        if self._d.deterministic_llm_factory is None:
            raise RuntimeError(
                "advance() requires deterministic_llm_factory; wire it from "
                "container.deterministic_llm in deps.py"
            )

        state.busy = True
        self._d.runner._d.llm = self._d.deterministic_llm_factory()

        try:
            last_frame = time.perf_counter()
            for minute in range(total_minutes):
                await self.tick(run_id)
                # Sessions are fire-and-forget; give them a slice to finish so
                # a fast-forward does not end with a hundred half-run tasks.
                if minute % 15 == 0:
                    await asyncio.sleep(0)

                if progress and (time.perf_counter() - last_frame) > 0.25:
                    last_frame = time.perf_counter()
                    await _maybe_await(
                        progress(
                            {
                                "sim_day": _sim_day(self._d.clock, state) - start_day,
                                "total_days": max(1, total_minutes // (24 * 60)),
                                "events_generated": (
                                    await self._d.emitter.current_seq(run_id) - start_seq
                                ),
                            }
                        )
                    )

            # Let outstanding sessions drain before reporting totals.
            for _ in range(50):
                if not state.active:
                    break
                await asyncio.sleep(0.02)

        finally:
            self._d.runner._d.llm = original_llm
            state.busy = False

        sim_date = _sim_date(self._d.clock)
        totals = await self._d.counters.read(run_id, "run", "", sim_date)
        end_seq = await self._d.emitter.current_seq(run_id)

        return {
            "sim_days_advanced": total_minutes / (24 * 60),
            "events_generated": end_seq - start_seq,
            "tasks": int(totals.get("requests", 0)),
            "tokens": int(totals.get("tokens", 0)),
            "cost_usd": round(float(totals.get("cost_usd", 0.0)), 2),
            "blocked": int(totals.get("blocked", 0)),
            "approvals": int(totals.get("review", 0)),
            "incidents_opened": 0,
            "duration_wall_ms": int((time.perf_counter() - started_wall) * 1000),
            "final_sim_ts": self._d.clock.sim_ts,
        }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _stable_order(employees: dict[str, Employee]) -> list[Employee]:
    """Sorted by id, always.

    Iterating a dict in insertion order works until the day something inserts
    in a different order, and then the same seed produces a different stream.
    Sorting costs nothing at twenty employees and removes the whole class.
    """
    return [employees[k] for k in sorted(employees)]


def _sim_day(clock: ClockPort, state: RunState) -> int:
    elapsed = clock.sim_ts - state.run.start_sim_ts
    return elapsed // 86_400 + 1


def _sim_hour(clock: ClockPort) -> int:
    if isinstance(clock, SimClock):
        return clock.sim_hour
    return (clock.sim_ts // 3600) % 24


def _sim_date(clock: ClockPort) -> str:
    if isinstance(clock, SimClock):
        return clock.sim_date
    from datetime import UTC, datetime

    return datetime.fromtimestamp(clock.sim_ts, tz=UTC).strftime("%Y-%m-%d")


def _in_work_hours(employee: Employee, hour: int) -> bool:
    start, end = employee.persona.work_hours
    return start <= hour < end


async def _maybe_await(value: Any) -> None:
    if asyncio.iscoroutine(value):
        await value


def _log_session_result(task: asyncio.Task[None]) -> None:
    """Surface a session's exception instead of letting it vanish silently.

    `_run_session` already catches and logs internally, so this fires only on
    the truly unexpected: a bug in the callback chain itself, or cancellation.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("session task raised", exc_info=exc)
