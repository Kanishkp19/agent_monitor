#!/usr/bin/env python
"""Train the IsolationForest on the trailing session window.

python tasks.py train-risk
"""

from __future__ import annotations

import argparse
import sys

from agentshield.deps import Services
from agentshield.scripts._common import heading, resolve_run, run


async def train(services: Services, *, run_id: str | None) -> int:
    resolved = await resolve_run(services, run_id)
    heading(f"training on {resolved}")
    result = await services.risk.train(resolved)

    if not result.get("trained"):
        print(f"  not enough sessions yet ({result.get('sessions', 0)})")
        print("  run: python tasks.py advance --days 30")
        return 0

    for key, value in result.items():
        print(f"  {key:<16} {value}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    return run(lambda s: train(s, run_id=args.run_id))


if __name__ == "__main__":
    sys.exit(main())
