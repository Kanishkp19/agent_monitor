"""EventBusPort -- fan-out for the telemetry stream.

The envelope is EventBridge-shaped already (`domain/events.py`), so moving from
the in-process bus to EventBridge changes the transport and nothing else.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from agentshield.domain.events import EventEnvelope

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


@runtime_checkable
class EventBusPort(Protocol):
    async def publish(self, envelope: EventEnvelope) -> None: ...

    def subscribe(self, handler: EventHandler, types: list[str] | None = None) -> None:
        """Register a handler, optionally filtered to specific `detail_type`s.

        Publication is fire-and-forget relative to the caller: a subscriber
        raising must never fail the governance decision that produced the event.
        """
        ...
