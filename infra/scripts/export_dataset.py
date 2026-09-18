#!/usr/bin/env python
"""Export the generated telemetry as a labelled ML dataset.

Features and labels go to **separate files**, deliberately. Anyone training on
`sessions.parquet` cannot accidentally pick up the answer, and anyone
evaluating has to make a conscious decision to open `labels.parquet`.

    python tasks.py export-dataset

Writes to `.data/export/`:
    sessions.parquet   the 12-feature session vectors
    events.parquet     the raw governed event stream
    labels.parquet     ground truth -- evaluation only
    DATASET-CARD.md    generation parameters and seed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from agentshield.container import get_container  # noqa: E402

OUT = Path(".data/export")


async def export(run_id: str | None) -> int:
    import pandas as pd

    container = get_container()
    await container.startup()
    store = container.docstore

    try:
        if not run_id:
            page = await store.query(pk="RUNS", index="gsi1", ascending=False, limit=1)
            if not page.items:
                print("No runs found. Run `python tasks.py seed` first.")
                return 1
            run_id = str(page.items[0].body["id"])

        run_item = await store.get(f"RUN#{run_id}", "META")
        run_body: dict[str, Any] = dict(run_item.body) if run_item else {}

        sessions = await store.query(pk=f"RUN#{run_id}", sk_prefix="SESSION#", limit=200_000)
        events = await store.query(pk=f"RUN#{run_id}", sk_prefix="EVT#", limit=200_000)
        labels = await store.query(pk=f"RUN#{run_id}", sk_prefix="GT#", limit=200_000)

        OUT.mkdir(parents=True, exist_ok=True)

        session_rows = [
            {
                "employee_id": item.body.get("employee_id"),
                "sim_ts": item.body.get("sim_ts"),
                "score": item.body.get("score"),
                **(item.body.get("features") or {}),
            }
            for item in sessions.items
        ]

        event_rows = [
            {
                "seq": item.body.get("detail", {}).get("seq"),
                "detail_type": item.body.get("detail_type"),
                "sim_ts": item.body.get("detail", {}).get("sim_ts"),
                "employee_id": item.body.get("detail", {}).get("employee_id"),
                "task_id": item.body.get("detail", {}).get("task_id"),
                "payload": json.dumps(item.body.get("detail", {}).get("payload", {})),
            }
            for item in events.items
        ]

        label_rows = [dict(item.body) for item in labels.items]

        pd.DataFrame(session_rows).to_parquet(OUT / "sessions.parquet", index=False)
        pd.DataFrame(event_rows).to_parquet(OUT / "events.parquet", index=False)
        pd.DataFrame(label_rows).to_parquet(OUT / "labels.parquet", index=False)

        card = build_card(
            run_id=run_id,
            run=run_body,
            sessions=len(session_rows),
            events=len(event_rows),
            labels=len(label_rows),
        )
        (OUT / "DATASET-CARD.md").write_text(card, encoding="utf-8")

        print(f"  sessions.parquet  {len(session_rows):>8,} rows")
        print(f"  events.parquet    {len(event_rows):>8,} rows")
        print(f"  labels.parquet    {len(label_rows):>8,} rows   (evaluation only)")
        print("  DATASET-CARD.md")
        print(f"\n  -> {OUT.resolve()}")
        return 0

    finally:
        await container.shutdown()


def build_card(
    *, run_id: str, run: dict[str, Any], sessions: int, events: int, labels: int
) -> str:
    generated = datetime.now(UTC).isoformat()
    lines = [
        "# AgentShield telemetry dataset",
        "",
        f"Generated {generated} from run `{run_id}`.",
        "",
        "## Generation parameters",
        "",
        "| | |",
        "|---|---|",
        f"| seed | `{run.get('seed')}` |",
        f"| employees | {run.get('employee_count')} |",
        f"| scenario | `{run.get('scenario')}` |",
        f"| simulated days | {run.get('sim_day')} |",
        "",
        "The seed is the whole dataset. Re-running with the same one reproduces",
        "these rows byte for byte: every draw in the simulator comes from a",
        "`random.Random` derived from it, and the fast-forward path forces a",
        "deterministic model regardless of configuration.",
        "",
        "## Files",
        "",
        "| File | Rows | Contents |",
        "|---|---|---|",
        f"| `sessions.parquet` | {sessions:,} | the 12-feature session vectors |",
        f"| `events.parquet` | {events:,} | the raw governed event stream |",
        f"| `labels.parquet` | {labels:,} | ground truth |",
        "",
        "## Using the labels",
        "",
        "**`labels.parquet` is for evaluation only.** The detector in this system",
        "is unsupervised by design: training on the adversarial label would make",
        "every precision and recall figure meaningless, because the model would",
        "have been told the answer.",
        "",
        "Nothing under `agentshield/risk/` can read these labels. It receives a",
        "store wrapper that raises on the key prefix they live under, and an",
        "import guard stops it reaching the modules that know which employee is",
        "adversarial. If you train on `sessions.parquet` and evaluate against",
        "`labels.parquet`, that separation holds for you too.",
        "",
        "## Known structure",
        "",
        "Two decoys exist so a detector cannot win by flagging any anomaly at all:",
        "",
        "- a **sloppy** employee with a high mistake rate and retry loops, who",
        "  burns budget without any malice;",
        "- a **release week** where devops and senior engineers genuinely spike.",
        "",
        "Flagging either is a false positive. A detector that scores well only by",
        "catching them has not found anything.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()
    return asyncio.run(export(args.run_id))


if __name__ == "__main__":
    sys.exit(main())
