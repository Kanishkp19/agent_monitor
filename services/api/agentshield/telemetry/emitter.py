"""The single choke point.

Every governed event in AgentShield passes through `TelemetryEmitter.emit()`.
No module writes to the event stream directly, and no module publishes to the
bus on its own. That constraint is what makes Simulation Mode and Live Mode
*provably* identical rather than nominally identical: there is one path, so
there is nothing to drift.

Two properties this file is responsible for:

**Ordering.** `seq` is a monotonic per-run counter assigned here. It is the
cursor for the Live Feed, the ordering key for replay, and the dedup key for
the WebSocket. Nothing orders by wall time; `sim_ts` is for display only.

**Label isolation.** `ground_truth` is written to `SK=GT#<seq>`, a key prefix
`RiskScopedDocStore` raises on. It is accepted only from `sim/` callers, and
read by exactly one file in the repository: `infra/scripts/evaluate.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

import ulid

from agentshield.domain.enums import Source
from agentshield.domain.events import EventDetail, EventEnvelope, GroundTruthRecord
from agentshield.ports.clock import ClockPort
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.ports.eventbus import EventBusPort
from agentshield.ports.metrics import MetricsPort

logger = logging.getLogger(__name__)

_MAX_WRITE_ATTEMPTS = 3
_DEAD_LETTER = Path(".data") / "dead-letter.jsonl"


class RiskObserver(Protocol):
    """Incremental feature accumulation. Deliberately narrow."""

    async def observe(self, envelope: EventEnvelope) -> None: ...


Broadcaster = Callable[[EventEnvelope], Awaitable[None]]


class TelemetryEmitter:
    def __init__(
        self,
        *,
        docstore: DocStorePort,
        bus: EventBusPort,
        metrics: MetricsPort,
        clock: ClockPort,
        source: Source = Source.SIM,
        risk: RiskObserver | None = None,
        broadcaster: Broadcaster | None = None,
        dead_letter_path: Path | None = None,
    ) -> None:
        self._docstore = docstore
        self._bus = bus
        self._metrics = metrics
        self._clock = clock
        self._source = source
        self._risk = risk
        self._broadcast = broadcaster
        self._dead_letter = dead_letter_path or _DEAD_LETTER
        self._seq_locks: dict[str, asyncio.Lock] = {}
        self.degraded = False
        """Set when an event could not be persisted after retries.

        Surfaces as a banner in the UI. Governance decisions are never blocked
        by a telemetry failure -- a control plane that stops deciding because
        its logger is down has failed twice.
        """

    # ── the one entry point ──────────────────────────────────────────

    async def emit(
        self,
        detail_type: str,
        *,
        run_id: str,
        payload: dict[str, Any],
        employee_id: str | None = None,
        task_id: str | None = None,
        ground_truth: dict[str, Any] | None = None,
    ) -> EventEnvelope:
        seq = await self._next_seq(run_id)

        envelope = EventEnvelope(
            id=f"evt_{ulid.new()}",
            source=f"agentshield.{self._source}",
            detail_type=detail_type,
            time=self._clock.now_wall().isoformat(),
            detail=EventDetail(
                run_id=run_id,
                seq=seq,
                sim_ts=self._clock.sim_ts,
                employee_id=employee_id,
                task_id=task_id,
                payload=payload,
            ),
        )

        # Durable first, and synchronously. Everything after this is
        # fire-and-forget: if the WebSocket is down, nothing else is affected,
        # which is the property the office's rehydration depends on.
        await self._persist(envelope)

        if ground_truth is not None:
            await self._persist_ground_truth(run_id, seq, ground_truth)

        await self._fan_out(envelope)
        return envelope

    # ── sequence ─────────────────────────────────────────────────────

    async def _next_seq(self, run_id: str) -> int:
        """Atomic per-run counter at `SEQ#<run_id>/EVENT`.

        Guarded by an in-process lock as well as the store's atomicity, so two
        coroutines in the same worker cannot interleave a read-modify-write.
        """
        lock = self._seq_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            item = await self._docstore.update(
                pk=f"SEQ#{run_id}", sk="EVENT", patch={"$add": {"value": 1}}
            )
            return int(item.body["value"])

    # ── persistence ──────────────────────────────────────────────────

    async def _persist(self, envelope: EventEnvelope) -> None:
        item = _event_item(envelope)
        for attempt in range(_MAX_WRITE_ATTEMPTS):
            try:
                await self._docstore.put(item)
                return
            except Exception as exc:
                if attempt == _MAX_WRITE_ATTEMPTS - 1:
                    self._to_dead_letter(envelope, exc)
                    return
                await asyncio.sleep(0.05 * (2**attempt))

    def _to_dead_letter(self, envelope: EventEnvelope, exc: Exception) -> None:
        """Last resort. The event is not lost, and governance continues."""
        self.degraded = True
        logger.error(
            "telemetry write failed; event sent to dead letter",
            extra={
                "detail_type": envelope.detail_type,
                "seq": envelope.detail.seq,
                "error": str(exc),
            },
        )
        try:
            self._dead_letter.parent.mkdir(parents=True, exist_ok=True)
            with self._dead_letter.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(envelope.model_dump(mode="json")) + "\n")
        except OSError:
            logger.exception("dead letter write failed")

    async def _persist_ground_truth(
        self, run_id: str, seq: int, ground_truth: dict[str, Any]
    ) -> None:
        record = GroundTruthRecord(run_id=run_id, seq=seq, **ground_truth)
        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run_id}",
                sk=f"GT#{seq:012d}",
                body=record.model_dump(mode="json"),
            )
        )

    # ── fan-out ──────────────────────────────────────────────────────

    async def _fan_out(self, envelope: EventEnvelope) -> None:
        """Bus, WebSocket, metrics, risk. None may fail the emit.

        A broken dashboard, a dropped socket or a slow feature accumulator
        must not be able to change what a gate decided, so every failure here
        is logged and swallowed.
        """
        for name, coro in (
            ("bus", self._bus.publish(envelope)),
            ("broadcast", self._broadcast(envelope) if self._broadcast else None),
            ("risk", self._risk.observe(envelope) if self._risk else None),
        ):
            if coro is None:
                continue
            try:
                await coro
            except Exception as exc:
                logger.warning(
                    "telemetry fan-out failed",
                    extra={"stage": name, "detail_type": envelope.detail_type, "error": str(exc)},
                )

        try:
            self._metrics.count(
                f"event.{envelope.detail_type}",
                run_id=envelope.detail.run_id,
                source=self._source,
            )
        except Exception:
            logger.debug("metrics emit failed", exc_info=True)

    # ── reads ────────────────────────────────────────────────────────

    async def read_page(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int = 200,
        detail_type: str | None = None,
        employee_id: str | None = None,
    ) -> list[EventEnvelope]:
        """A10/A11/A12 -- the Live Feed's page and its two filtered variants."""
        if detail_type:
            page = await self._docstore.query(
                pk=f"RUN#{run_id}#TYPE#{detail_type}",
                index="gsi1",
                sk_between=(f"{since_seq + 1:012d}", "999999999999"),
                limit=limit,
            )
        elif employee_id:
            page = await self._docstore.query(
                pk=f"RUN#{run_id}#EMP#{employee_id}#EVT",
                index="gsi2",
                sk_between=(f"{since_seq + 1:012d}", "999999999999"),
                limit=limit,
            )
        else:
            page = await self._docstore.query(
                pk=f"RUN#{run_id}",
                sk_between=(f"EVT#{since_seq + 1:012d}", "EVT#999999999999"),
                limit=limit,
            )
        return [EventEnvelope.model_validate(item.body) for item in page.items]

    async def current_seq(self, run_id: str) -> int:
        item = await self._docstore.get(f"SEQ#{run_id}", "EVENT")
        return int(item.body.get("value", 0)) if item else 0


def _event_item(envelope: EventEnvelope) -> DocItem:
    """Key layout from `docs/05-BACKEND-SCHEMA.md` section 3.1.

    Zero-padding the sequence is load-bearing: it makes lexicographic sort-key
    ordering equal numeric ordering, which is how DynamoDB range queries work.
    """
    detail = envelope.detail
    seq = f"{detail.seq:012d}"
    return DocItem(
        pk=f"RUN#{detail.run_id}",
        sk=f"EVT#{seq}",
        gsi1pk=f"RUN#{detail.run_id}#TYPE#{envelope.detail_type}",
        gsi1sk=seq,
        gsi2pk=(
            f"RUN#{detail.run_id}#EMP#{detail.employee_id}#EVT" if detail.employee_id else None
        ),
        gsi2sk=seq if detail.employee_id else None,
        body=envelope.model_dump(mode="json"),
    )
