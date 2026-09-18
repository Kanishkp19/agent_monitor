#!/usr/bin/env python
"""Drive one agent task end to end through both gates.

    python tasks.py run-task --employee emp_013 --task "Fix payment API error" \
        --repo payments-api --env production

Prints each tool call and its governed outcome, which is the fastest way to
see the agent loop and the gates interacting without a browser open.
"""

from __future__ import annotations

import argparse
import sys

import ulid

from agentshield.deps import Services
from agentshield.domain.enums import Environment, TaskStatus
from agentshield.domain.models import Task
from agentshield.scripts._common import heading, resolve_run, run


async def run_task(
    services: Services,
    *,
    run_id: str | None,
    employee_id: str,
    title: str,
    repo: str | None,
    environment: str | None,
) -> int:
    resolved = await resolve_run(services, run_id)
    sim_run = await services.seeder.load_run(resolved)
    if sim_run is None:
        raise SystemExit(f"no run {resolved}")
    if services.engine.state(resolved) is None:
        await services.engine.attach(sim_run)

    employee = await services.seeder.load_employee(resolved, employee_id)
    if employee is None:
        raise SystemExit(f"no employee {employee_id}")

    target_repo = repo or (employee.persona.allowed_repositories or ["payments-api"])[0]

    task = Task(
        id=f"task_{ulid.new().str[-8:].lower()}",
        run_id=resolved,
        employee_id=employee_id,
        title=title,
        task_type="data_access",
        complexity="standard",
        repo=target_repo,
        environment=Environment(environment or "local"),
        status=TaskStatus.WORKING,
        started_sim_ts=services.container.clock.sim_ts,
        prompt_text=title,
    )

    heading(f"{employee.name} ({employee.role}) -- {title}")
    print(f"  repo {target_repo}  env {task.environment}\n")

    before = await services.emitter.current_seq(resolved)
    state = services.engine.state(resolved)
    actor = await services.engine._build_actor(state, employee)
    await services.runner.run(task, actor)

    events = await services.emitter.read_page(resolved, since_seq=before, limit=200)
    for event in events:
        payload = event.detail.payload
        if event.detail_type == "gate2.decision":
            print(
                f"  {payload.get('tool', ''):<16} "
                f"{payload.get('target_resource', '')!s:<40} "
                f"{str(payload.get('decision', '')).upper():<7} "
                f"{_policy(payload)}"
            )
        elif event.detail_type == "model.invoked":
            print(
                f"  {'model':<16} {payload.get('model_id', ''):<40} "
                f"{payload.get('input_tokens', 0)}in/{payload.get('output_tokens', 0)}out"
            )

    print(f"\n  status      {task.status}")
    print(f"  actions     {task.actions_total} ({task.actions_blocked} blocked)")
    print(f"  cost        ${task.cost_usd:.4f}")
    return 0


def _policy(payload: dict) -> str:
    matches = payload.get("matched_policies") or []
    return matches[0].get("policy_id", "") if matches else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--employee", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--repo", default=None)
    parser.add_argument("--env", default=None)
    args = parser.parse_args()

    return run(
        lambda s: run_task(
            s,
            run_id=args.run_id,
            employee_id=args.employee,
            title=args.task,
            repo=args.repo,
            environment=args.env,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
