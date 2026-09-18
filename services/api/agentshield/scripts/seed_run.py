#!/usr/bin/env python
"""Seed a run.

python tasks.py seed
python tasks.py seed-policies     # policies only, for Phase 2 work
"""

from __future__ import annotations

import argparse
import sys

from agentshield.deps import Services
from agentshield.scripts._common import heading, run


async def seed(services: Services, *, policies_only: bool, seed_value: int | None) -> int:
    if policies_only:
        policies = await services.seeder.seed_policies()
        heading("policies seeded")
        for policy in policies:
            flag = "draft" if policy.is_draft else f"v{policy.version}"
            print(
                f"  gate{int(policy.gate)}  {str(policy.effect).upper():<7} "
                f"p{policy.priority:<4} {policy.id:<36} {flag}"
            )
        print(f"\n  {len(policies)} policies")
        return 0

    settings = services.container.settings
    sim_run, employees = await services.seeder.create_run(
        seed=seed_value if seed_value is not None else settings.sim_seed,
        employee_count=settings.sim_employee_count,
        speed=int(settings.sim_default_speed),
        start_sim_ts=settings.sim_start_ts,
    )
    await services.engine.attach(sim_run)

    heading(f"run {sim_run.id}")
    print(f"  seed        {sim_run.seed}")
    print(f"  employees   {len(employees)}")
    print(f"  sim start   {sim_run.sim_ts}")
    print("\n  next: python tasks.py seed-history")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policies-only", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    return run(
        lambda services: seed(services, policies_only=args.policies_only, seed_value=args.seed)
    )


if __name__ == "__main__":
    sys.exit(main())
