"""Simulation control: create, read, control, advance, snapshot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from agentshield.api.schemas import AdvanceRequest, ControlRequest, CreateRunRequest, ok
from agentshield.deps import Services, get_services
from agentshield.domain.enums import SimSpeed
from agentshield.domain.errors import RunBusy, RunNotFound
from agentshield.sim.clock import SimClock

router = APIRouter(prefix="/sim", tags=["simulation"])


@router.post("/runs", status_code=201)
async def create_run(
    body: CreateRunRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Create and seed a run: 20 employees, 6 repos with file trees, 12 policies."""
    settings = services.container.settings
    run, employees = await services.seeder.create_run(
        seed=body.seed if body.seed is not None else settings.sim_seed,
        employee_count=body.employee_count,
        speed=body.speed,
        scenario=body.scenario,
        start_sim_ts=body.start_sim_ts or settings.sim_start_ts,
    )

    if isinstance(services.container.clock, SimClock):
        services.container.clock._sim_ts = run.start_sim_ts
        services.container.clock.set_speed(SimSpeed(body.speed))

    await services.engine.attach(run)

    if body.seed_history:
        # 14 simulated days so risk baselines exist. Without this every
        # employee stays `low_confidence` and the risk screen has nothing to
        # say -- which reads as a broken feature rather than an empty one.
        await services.engine.advance(run.id, sim_days=14)

    return ok(
        {
            "run_id": run.id,
            "seed": run.seed,
            "employee_count": len(employees),
            "speed": run.speed,
            "sim_ts": run.sim_ts,
            "scenario": run.scenario,
            "employees": [e.to_public().model_dump(mode="json") for e in employees],
        }
    )


@router.get("/runs")
async def list_runs(services: Services = Depends(get_services)) -> dict[str, Any]:
    runs = await services.seeder.recent_runs()
    return ok([r.model_dump(mode="json") for r in runs])


@router.get("/runs/{run_id}")
async def get_run(run_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    run = await services.seeder.load_run(run_id)
    if run is None:
        raise RunNotFound(f"no run {run_id!r}")
    return ok(run.model_dump(mode="json"))


@router.post("/runs/{run_id}/control")
async def control_run(
    run_id: str, body: ControlRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    run = await services.seeder.load_run(run_id)
    if run is None:
        raise RunNotFound(f"no run {run_id!r}")

    state = services.engine.state(run_id) or await services.engine.attach(run)

    # A control action during a 100x batch would desync the frame sequence the
    # client is reconciling against. Pause is allowed, because stopping a
    # runaway fast-forward must always be possible.
    if state.busy and body.action != "pause":
        raise RunBusy("a fast-forward is in progress")

    if body.action == "start":
        await services.engine.start(run_id)
    elif body.action == "pause":
        await services.engine.pause(run_id)
    elif body.action == "resume":
        await services.engine.start(run_id)
    elif body.action == "set_speed" and body.speed is not None:
        services.engine.set_speed(run_id, SimSpeed(body.speed))
        if body.speed != 0:
            await services.engine.start(run_id)
    elif body.action == "reset":
        await services.engine.pause(run_id)

    state = services.engine.state(run_id)
    status = "paused" if (state and state.paused) else "running"
    if body.action == "reset":
        status = "reset"

    return ok(
        {
            "run_id": run_id,
            "status": status,
            "speed": state.run.speed if state else run.speed,
            "sim_ts": services.container.clock.sim_ts,
        }
    )


@router.post("/runs/{run_id}/advance")
async def advance_run(
    run_id: str, body: AdvanceRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Headless fast-forward.

    Streams progress frames over the WebSocket and returns the summary. Forces
    MockLLM for the duration regardless of provider.
    """
    run = await services.seeder.load_run(run_id)
    if run is None:
        raise RunNotFound(f"no run {run_id!r}")

    if services.engine.state(run_id) is None:
        await services.engine.attach(run)

    async def on_progress(progress: dict[str, Any]) -> None:
        await services.hub.send({"kind": "progress", "seq": 0, "progress": progress})

    summary = await services.engine.advance(
        run_id, sim_days=body.sim_days, sim_hours=body.sim_hours, progress=on_progress
    )
    return ok(summary)


@router.get("/runs/{run_id}/state")
async def get_state(run_id: str, services: Services = Depends(get_services)) -> dict[str, Any]:
    """The office snapshot, used for mount and rehydration."""
    run = await services.seeder.load_run(run_id)
    if run is None:
        raise RunNotFound(f"no run {run_id!r}")

    state = services.engine.state(run_id) or await services.engine.attach(run)
    employees = list(state.employees.values())
    seq = await services.emitter.current_seq(run_id)

    snapshot = await services.snapshots.build(
        run_id=run_id,
        seq=seq,
        sim_ts=services.container.clock.sim_ts,
        speed=state.run.speed,
        employees=employees,
        active=state.active,
    )
    return ok(snapshot.model_dump(mode="json"))
