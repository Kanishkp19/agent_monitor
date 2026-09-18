"""QueuePort contract -- runs against asyncio.Queue and SQS."""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.contract


async def test_enqueue_then_dequeue(queue: Any) -> None:
    await queue.enqueue({"task_id": "task_9c21", "employee_id": "emp_017"})
    messages = await queue.dequeue(max_messages=1)
    assert messages == [{"task_id": "task_9c21", "employee_id": "emp_017"}]


async def test_dequeue_on_empty_returns_empty_list(queue: Any) -> None:
    """Never blocks forever, never raises -- the tick loop calls this every tick."""
    assert await queue.dequeue(max_messages=1) == []


async def test_dequeue_takes_at_most_max_messages(queue: Any) -> None:
    for i in range(5):
        await queue.enqueue({"i": i})
    first = await queue.dequeue(max_messages=3)
    assert len(first) <= 3


async def test_messages_are_taken_once(queue: Any) -> None:
    await queue.enqueue({"i": 1})
    await queue.dequeue(max_messages=10)
    assert await queue.dequeue(max_messages=10) == []


async def test_payloads_survive_the_round_trip(queue: Any) -> None:
    payload = {"task_id": "t1", "nested": {"repo": "payments-api", "cost": 0.014}, "n": 3}
    await queue.enqueue(payload)
    assert (await queue.dequeue(max_messages=1))[0] == payload
