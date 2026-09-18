#!/usr/bin/env python
"""Detection evaluation.

**This is the only file in the repository permitted to read `GT#` keys.**

Everything under `agentshield/risk/` receives a `RiskScopedDocStore` that
raises on those keys, and `tests/test_architecture.py` forbids `risk/` from
importing the modules that know which employee is adversarial. This script
uses the unwrapped store, after the fact, to score what the detector found.

That separation is the whole point. A detector trained on the label would
report whatever recall you wanted; a detector that has never seen the label
reports something you can act on.

    python tasks.py evaluate
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))

from agentshield.container import get_container  # noqa: E402
from agentshield.domain.enums import ScenarioProfile  # noqa: E402

FLAG_THRESHOLD = 70


@dataclass
class Evaluation:
    sessions: int = 0
    flagged: int = 0
    adversarial_ids: list[str] = None  # type: ignore[assignment]
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    fp_sloppy: int = 0
    fp_release_week: int = 0
    time_to_detection_days: float | None = None

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 0.0

    @property
    def fp_rate(self) -> float:
        return self.false_positives / self.sessions if self.sessions else 0.0


async def evaluate(run_id: str) -> Evaluation:
    container = get_container()
    await container.startup()
    store = container.docstore  # unwrapped, deliberately

    try:
        # ── the labels ───────────────────────────────────────────────
        # A24. Called here and nowhere else in the codebase.
        truth = await store.query(pk=f"RUN#{run_id}", sk_prefix="GT#", limit=50_000)

        adversarial: set[str] = set()
        sloppy: set[str] = set()
        first_stage2_ts: int | None = None

        for item in truth.items:
            body = item.body
            employee_id = str(body.get("employee_id", ""))
            profile = str(body.get("scenario_profile", ""))

            if profile == str(ScenarioProfile.ADVERSARIAL):
                adversarial.add(employee_id)
                # "Stage 2" is the recon rung -- the first behaviour that is
                # genuinely detectable. Time-to-detection is measured from
                # there, not from day one, because day one is by construction
                # indistinguishable.
                if body.get("stage") == "recon" and first_stage2_ts is None:
                    first_stage2_ts = int(body.get("seq", 0))
            elif profile == str(ScenarioProfile.SLOPPY):
                sloppy.add(employee_id)

        # ── what the detector said ───────────────────────────────────
        sessions = await store.query(pk=f"RUN#{run_id}", sk_prefix="SESSION#", limit=50_000)

        result = Evaluation(adversarial_ids=sorted(adversarial))
        detected_at: int | None = None

        for item in sessions.items:
            body = item.body
            employee_id = str(body.get("employee_id", ""))
            score = int(body.get("score", 0))
            sim_ts = int(body.get("sim_ts", 0))

            result.sessions += 1
            flagged = score >= FLAG_THRESHOLD
            is_adversarial = employee_id in adversarial

            if flagged:
                result.flagged += 1

            if flagged and is_adversarial:
                result.true_positives += 1
                if detected_at is None or sim_ts < detected_at:
                    detected_at = sim_ts
            elif flagged and not is_adversarial:
                result.false_positives += 1
                if employee_id in sloppy:
                    result.fp_sloppy += 1
                else:
                    # Release week is days 9-10. A spike there is legitimate,
                    # and counting it honestly is more useful than tuning it
                    # away -- it is the most interesting failure mode the
                    # system has.
                    day = _sim_day(sim_ts, sessions.items)
                    if day in (9, 10):
                        result.fp_release_week += 1
            elif not flagged and is_adversarial:
                result.false_negatives += 1

        if detected_at is not None:
            ladder_start = _first_recon_ts(sessions.items, adversarial)
            if ladder_start:
                result.time_to_detection_days = round(
                    (detected_at - ladder_start) / 86_400, 1
                )

        return result

    finally:
        await container.shutdown()


def _sim_day(sim_ts: int, items: list) -> int:  # type: ignore[type-arg]
    if not items:
        return 0
    start = min(int(i.body.get("sim_ts", sim_ts)) for i in items)
    return (sim_ts - start) // 86_400 + 1


def _first_recon_ts(items: list, adversarial: set[str]) -> int | None:  # type: ignore[type-arg]
    """Roughly when the ladder became detectable: the adversary's day 4."""
    if not items:
        return None
    start = min(int(i.body.get("sim_ts", 0)) for i in items)
    return start + 3 * 86_400 if adversarial else None


def report(result: Evaluation) -> None:
    line = "-" * 50
    print(f"\n-- AgentShield detection evaluation {line[:14]}")
    print(f"  sessions            {result.sessions:>6,}")
    print(f"  flagged (>={FLAG_THRESHOLD})       {result.flagged:>6,}")
    print(f"  adversarial actor   {', '.join(result.adversarial_ids) or 'none'}")
    print(f"  recall              {result.recall:>6.2f}")
    print(f"  precision           {result.precision:>6.2f}")
    print(
        f"  false positives     {result.false_positives:>6,}   "
        f"(sloppy-intern {result.fp_sloppy}, release-week {result.fp_release_week})"
    )
    print(f"  false-positive rate {result.fp_rate:>6.2f}")
    if result.time_to_detection_days is not None:
        print(f"  time to detection   {result.time_to_detection_days:>6.1f} simulated days")
    print(f"{line}\n")

    # The targets from `docs/01-PRD.md` Success Metrics, stated so a run
    # either meets them or visibly does not.
    checks = [
        ("recall >= 0.80", result.recall >= 0.80),
        ("false-positive rate <= 0.05", result.fp_rate <= 0.05),
        (
            "time to detection <= 2 days",
            result.time_to_detection_days is None or result.time_to_detection_days <= 2.0,
        ),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    print()

    if result.recall >= 0.99:
        print("  Recall of ~1.0 usually means label leakage.")
        print("  Run: pytest tests/test_no_label_leakage.py\n")
    elif result.recall < 0.2:
        print("  Near-zero recall: the ladder may be too subtle, or the")
        print("  training window may exclude the escalation.\n")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", help="run to evaluate (default: most recent)")
    args = parser.parse_args()

    run_id = args.run_id
    if not run_id:
        container = get_container()
        await container.startup()
        page = await container.docstore.query(
            pk="RUNS", index="gsi1", ascending=False, limit=1
        )
        await container.shutdown()
        if not page.items:
            print("No runs found. Run `python tasks.py seed` first.")
            return 1
        run_id = str(page.items[0].body["id"])

    print(f"evaluating {run_id}")
    report(await evaluate(run_id))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
