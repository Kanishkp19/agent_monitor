"""EventBridge implementation of EventBusPort.

The envelope needs no translation -- `domain/events.py` is EventBridge-shaped
already. That is the payoff of adopting the model instead of abstracting it:
this adapter is a transport, not a mapper.

`subscribe()` is a no-op by design. On AWS, subscription is a *rule*, declared
in `infra/aws/eventbridge-rules.yaml`, not a runtime registration. Silently
accepting the call keeps `container.py` free of environment branches beyond the
one it already has.
"""

from __future__ import annotations

import asyncio
import json
import logging

import boto3

from agentshield.domain.events import EventEnvelope
from agentshield.ports.eventbus import EventHandler

logger = logging.getLogger(__name__)


class EventBridgeBus:
    def __init__(self, bus_name: str, region: str, client: object | None = None) -> None:
        self._bus = bus_name
        self._client = client if client is not None else boto3.client("events", region_name=region)
        self._local_handlers: list[tuple[EventHandler, frozenset[str] | None]] = []

    def subscribe(self, handler: EventHandler, types: list[str] | None = None) -> None:
        """Register an in-process handler in addition to the bus.

        The risk engine and the WebSocket broadcaster live in this process even
        when the bus is remote, so they still need delivery. Cross-service
        subscribers use EventBridge rules instead.
        """
        self._local_handlers.append((handler, frozenset(types) if types else None))

    async def publish(self, envelope: EventEnvelope) -> None:
        entry = {
            "Source": envelope.source,
            "DetailType": envelope.detail_type,
            "Detail": json.dumps(envelope.detail.model_dump(mode="json")),
            "EventBusName": self._bus,
        }
        response = await asyncio.to_thread(self._client.put_events, Entries=[entry])
        if response.get("FailedEntryCount"):
            logger.warning(
                "eventbridge rejected an entry",
                extra={
                    "detail_type": envelope.detail_type,
                    "seq": envelope.detail.seq,
                    "entries": response.get("Entries"),
                },
            )

        matching = [
            h for h, types in self._local_handlers if types is None or envelope.detail_type in types
        ]
        if not matching:
            return
        results = await asyncio.gather(
            *(handler(envelope) for handler in matching), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                logger.warning("event subscriber failed", extra={"error": str(result)})
