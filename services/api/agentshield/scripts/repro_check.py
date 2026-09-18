#!/usr/bin/env python
"""Run the same seed twice and compare event-stream hashes.

    python tasks.py repro-check

If this fails, stop and find the cause before doing anything else. A
non-reproducible simulation cannot be debugged, cannot be demoed reliably, and
makes every number the detector reports meaningless.

The three usual causes, in order of likelihood:
  1. a module-level `random` call instead of a seeded `random.Random`
  2. iteration over a `set`
  3. dependence on dict insertion order somewhere in a seeded path
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from agentshield.deps import Services
from agentshield.scripts._common import heading, run


async def stream_hash(services: Services, *, seed: int, days: int) -> tuple[str, int]:
    sim_run, _ = await services.seeder.create_run(
        seed=seed,
        employee_count=services.container.settings.sim_employee_count,
        start_sim_ts=services.container.settings.sim_start_ts,
    )
    await services.engine.attach(sim_run)
    await services.engine.advance(sim_run.id, sim_days=days)

    page = await services.container.docstore.query(
        pk=f"RUN#{sim_run.id}", sk_prefix="EVT#", limit=100_000
    )

    digest = hashlib.sha256()
    for item in page.items:
        envelope = item.body
        detail = envelope.get("detail", {})
        # Hash the governed facts, not the incidental ones. Event ids are
        # ULIDs and `time` is wall clock -- both differ between runs by
        # design and neither is part of what reproducibility means here.
        digest.update(
            json.dumps(
                {
                    "seq": detail.get("seq"),
                    "type": envelope.get("detail_type"),
                    "sim_ts": detail.get("sim_ts"),
                    "employee_id": detail.get("employee_id"),
                    "payload": detail.get("payload"),
                },
                sort_keys=True,
            ).encode()
        )

    return digest.hexdigest(), page.count


async def check(services: Services, *, seed: int, days: int) -> int:
    heading(f"reproducibility check (seed {seed}, {days} sim-day(s))")

    first, count_a = await stream_hash(services, seed=seed, days=days)
    print(f"  run 1: {first[:16]}...  {count_a:,} events")

    second, count_b = await stream_hash(services, seed=seed, days=days)
    print(f"  run 2: {second[:16]}...  {count_b:,} events")

    if first == second:
        print("\n  identical -- reproducible")
        return 0

    print("\n  STREAMS DIFFER")
    print("  Look for: module-level random, set iteration, dict ordering.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--days", type=int, default=2)
    args = parser.parse_args()
    return run(lambda s: check(s, seed=args.seed, days=args.days))


if __name__ == "__main__":
    sys.exit(main())
