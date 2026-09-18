#!/usr/bin/env python
"""Fast-forward the simulation headlessly.

python tasks.py advance --days 7
python tasks.py seed-history        # 14 days, so baselines exist
"""

from __future__ import annotations

import argparse
import sys
import time

from agentshield.deps import Services
from agentshield.scripts._common import heading, resolve_run, run


async def advance(services: Services, *, run_id: str | None, days: int) -> int:
    resolved = await resolve_run(services, run_id)
    sim_run = await services.seeder.load_run(resolved)
    if sim_run is None:
        raise SystemExit(f"no run {resolved}")

    if services.engine.state(resolved) is None:
        await services.engine.attach(sim_run)

    heading(f"advancing {resolved} by {days} simulated day(s)")
    started = time.perf_counter()
    summary = await services.engine.advance(resolved, sim_days=days)
    wall = time.perf_counter() - started

    for key in (
        "sim_days_advanced",
        "events_generated",
        "tasks",
        "tokens",
        "cost_usd",
        "blocked",
        "approvals",
    ):
        print(f"  {key:<20} {summary.get(key, 0)}")
    print(f"  {'wall seconds':<20} {wall:.1f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--days", type=int, default=1)
    args = parser.parse_args()
    return run(lambda s: advance(s, run_id=args.run_id, days=args.days))


if __name__ == "__main__":
    sys.exit(main())
