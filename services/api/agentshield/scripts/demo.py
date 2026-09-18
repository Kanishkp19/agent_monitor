#!/usr/bin/env python
"""The scripted three-minute demo, unattended.

    python tasks.py demo

Seeds a run, pre-runs history so risk baselines exist, advances through the
adversarial ladder, trains the detector and prints the beats. Identical every
time, because the seed is fixed and `advance()` forces MockLLM.
"""

from __future__ import annotations

import argparse
import sys
import time

from agentshield.deps import Services
from agentshield.scripts._common import heading, run


async def demo(services: Services, *, seed: int) -> int:
    settings = services.container.settings
    started = time.perf_counter()

    heading("1/5  seeding Acme Payments")
    sim_run, employees = await services.seeder.create_run(
        seed=seed, employee_count=20, start_sim_ts=settings.sim_start_ts
    )
    await services.engine.attach(sim_run)
    print(f"  run {sim_run.id}: {len(employees)} employees, 6 repos, 13 policies")

    heading("2/5  building baselines (14 simulated days)")
    await services.engine.advance(sim_run.id, sim_days=14)
    print("  every employee now has history to be compared against")

    heading("3/5  running the adversarial ladder (16 more days)")
    summary = await services.engine.advance(sim_run.id, sim_days=16)
    print(f"  {summary['events_generated']:,} events, {summary['tasks']:,} tasks")
    print(f"  {summary['blocked']} blocked actions, {summary['approvals']} approvals")
    print(f"  ${summary['cost_usd']:.2f} simulated spend")

    heading("4/5  training the detector")
    result = await services.risk.train(sim_run.id)
    if result.get("trained"):
        print(f"  IsolationForest on {result['sessions']:,} sessions, 12 features")
        print("  the model has never seen a label")
    else:
        print(f"  not enough sessions ({result.get('sessions', 0)})")

    heading("5/5  what the detector found")
    page = await services.container.docstore.query(
        pk=f"RUN#{sim_run.id}#RISKRANK", index="gsi1", ascending=False, limit=5
    )
    for item in page.items:
        body = item.body
        name = body.get("employee_id", "")
        print(f"  {name:<10} risk {body.get('score', 0):>3}  ({body.get('confidence')})")
        for factor in (body.get("top_factors") or [])[:3]:
            print(f"      - {factor.get('explanation', '')}")

    incidents = await services.container.docstore.query(
        pk=f"RUN#{sim_run.id}#INC#open", index="gsi1", limit=10
    )
    print(f"\n  {incidents.count} open incident(s)")

    print(f"\n  run id: {sim_run.id}")
    print(f"  wall time: {time.perf_counter() - started:.1f}s")
    print("\n  next: python tasks.py evaluate")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260918)
    args = parser.parse_args()
    return run(lambda s: demo(s, seed=args.seed))


if __name__ == "__main__":
    sys.exit(main())
