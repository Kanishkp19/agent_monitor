"""asyncio.Queue implementation of QueuePort.

Stands in for SQS while the simulation runs in one process. `dequeue` mirrors
SQS long-polling: it returns up to `max_messages`, waits at most
`wait_seconds`, and returns an empty list rather than blocking forever.
"""

from __future__ import annotations

import asyncio
from typing import Any


class AsyncioQueue:
    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def enqueue(self, msg: dict[str, Any]) -> None:
        await self._queue.put(msg)

    async def dequeue(self, max_messages: int = 1, wait_seconds: int = 0) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        try:
            first = (
                await asyncio.wait_for(self._queue.get(), timeout=wait_seconds)
                if wait_seconds
                else self._queue.get_nowait()
            )
            messages.append(first)
        except (TimeoutError, asyncio.QueueEmpty):
            return messages

        # Drain whatever else is already waiting, without blocking again.
        while len(messages) < max_messages:
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    def qsize(self) -> int:
        return self._queue.qsize()
