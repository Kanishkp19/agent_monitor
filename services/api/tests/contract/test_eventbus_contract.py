"""EventBusPort contract -- runs against the in-process bus and EventBridge.

The critical property is not delivery, it is *isolation*: a subscriber that
raises must not propagate back to the publisher. Telemetry fan-out sits
downstream of a governance decision that has already been made, and a broken
dashboard must never be able to change what a gate decided.
"""

from __future__ import annotations

from typing import Any

import pytest

from agentshield.domain.events import EventDetail, EventEnvelope

pytestmark = pytest.mark.contract


def _envelope(seq: int = 1, detail_type: str = "gate2.decision") -> EventEnvelope:
    return EventEnvelope(
        id=f"evt_{seq:04d}",
        source="agentshield.sim",
        detail_type=detail_type,
        time="2026-09-18T09:21:04Z",
        detail=EventDetail(
            run_id="r1",
            seq=seq,
            sim_ts=1758182464,
            employee_id="emp_017",
            task_id="task_9c21",
            payload={"decision": "block", "tool": "read_file"},
        ),
    )


async def test_publish_reaches_a_subscriber(eventbus: Any) -> None:
    received: list[EventEnvelope] = []

    async def handler(env: EventEnvelope) -> None:
        received.append(env)

    eventbus.subscribe(handler)
    await eventbus.publish(_envelope())

    assert [e.detail.seq for e in received] == [1]


async def test_publish_with_no_subscribers_is_fine(eventbus: Any) -> None:
    await eventbus.publish(_envelope())


async def test_type_filter_is_respected(eventbus: Any) -> None:
    gate_events: list[str] = []
    all_events: list[str] = []

    async def only_gate2(env: EventEnvelope) -> None:
        gate_events.append(env.detail_type)

    async def everything(env: EventEnvelope) -> None:
        all_events.append(env.detail_type)

    eventbus.subscribe(only_gate2, types=["gate2.decision"])
    eventbus.subscribe(everything)

    await eventbus.publish(_envelope(1, "gate2.decision"))
    await eventbus.publish(_envelope(2, "task.completed"))

    assert gate_events == ["gate2.decision"]
    assert all_events == ["gate2.decision", "task.completed"]


async def test_a_raising_subscriber_does_not_break_publish(eventbus: Any) -> None:
    """The property the whole telemetry design depends on."""
    survived: list[int] = []

    async def explodes(env: EventEnvelope) -> None:
        raise RuntimeError("subscriber is broken")

    async def works(env: EventEnvelope) -> None:
        survived.append(env.detail.seq)

    eventbus.subscribe(explodes)
    eventbus.subscribe(works)

    await eventbus.publish(_envelope(7))  # must not raise

    assert survived == [7]


async def test_ordering_is_preserved_per_publisher(eventbus: Any) -> None:
    seen: list[int] = []

    async def handler(env: EventEnvelope) -> None:
        seen.append(env.detail.seq)

    eventbus.subscribe(handler)
    for seq in range(1, 6):
        await eventbus.publish(_envelope(seq))

    assert seen == [1, 2, 3, 4, 5]
