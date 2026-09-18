#!/usr/bin/env python
"""Print stored event keys for a run.

Replaces the `sqlite3` CLI check in the docs, which assumed a binary this
project does not require:

    sqlite3 .data/agentshield.db "SELECT sk FROM items WHERE pk='RUN#x'..."
    python tasks.py inspect-events --run-id run_x
"""

from __future__ import annotations

import argparse
import sys

from agentshield.deps import Services
from agentshield.scripts._common import heading, resolve_run, run


async def inspect(services: Services, *, run_id: str | None, limit: int) -> int:
    resolved = await resolve_run(services, run_id)
    page = await services.container.docstore.query(
        pk=f"RUN#{resolved}", sk_prefix="EVT#", limit=limit
    )

    heading(f"{resolved}: first {page.count} events")
    for item in page.items:
        envelope = item.body
        detail = envelope.get("detail", {})
        print(
            f"  {item.sk}  {envelope.get('detail_type', ''):<22} "
            f"emp={detail.get('employee_id') or '-':<10} "
            f"task={detail.get('task_id') or '-'}"
        )

    total = await services.emitter.current_seq(resolved)
    print(f"\n  {total} events total")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    return run(lambda s: inspect(s, run_id=args.run_id, limit=args.limit))


if __name__ == "__main__":
    sys.exit(main())
