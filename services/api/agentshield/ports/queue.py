"""QueuePort -- fan-out for agent sessions.

Only used to distribute agent sessions. Locally the simulation engine runs
them in-process, so this is an `asyncio.Queue`; on AWS it is SQS with workers.
No broker is needed for a single-process build, and swapping to one is a
container change rather than a rewrite.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class QueuePort(Protocol):
    async def enqueue(self, msg: dict[str, Any]) -> None: ...

    async def dequeue(
        self, max_messages: int = 1, wait_seconds: int = 0
    ) -> list[dict[str, Any]]: ...
