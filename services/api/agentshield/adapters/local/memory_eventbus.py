"""In-process pub/sub implementation of EventBusPort, with a SQLite outbox.

The outbox exists so that local behaviour matches EventBridge's delivery
guarantee rather than Python's: an event that was published is durably recorded
even if every subscriber throws, and can be replayed.

A subscriber raising is logged and swallowed. Publication is downstream of the
governance decision that produced the event -- a broken dashboard must never
change what a gate decided.
"""

from __future__ import annotations

import asyncio
import logging

from agentshield.domain.events import EventEnvelope
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.ports.eventbus import EventHandler

logger = logging.getLogger(__name__)


class MemoryBus:
    def __init__(self, outbox: DocStorePort | None = None) -> None:
        self._subscribers: list[tuple[EventHandler, frozenset[str] | None]] = []
        self._outbox = outbox

    def subscribe(self, handler: EventHandler, types: list[str] | None = None) -> None:
        self._subscribers.append((handler, frozenset(types) if types else None))

    async def publish(self, envelope: EventEnvelope) -> None:
        if self._outbox is not None:
            await self._outbox.put(_outbox_item(envelope))

        matching = [
            handler
            for handler, types in self._subscribers
            if types is None or envelope.detail_type in types
        ]
        if not matching:
            return

        results = await asyncio.gather(
            *(handler(envelope) for handler in matching), return_exceptions=True
        )
        for handler, result in zip(matching, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "event subscriber failed",
                    extra={
                        "handler": getattr(handler, "__qualname__", repr(handler)),
                        "detail_type": envelope.detail_type,
                        "seq": envelope.detail.seq,
                        "error": str(result),
                    },
                )


def _outbox_item(envelope: EventEnvelope) -> DocItem:
    return DocItem(
        pk=f"OUTBOX#{envelope.detail.run_id}",
        sk=f"MSG#{envelope.detail.seq:012d}",
        body=envelope.model_dump(mode="json"),
    )
