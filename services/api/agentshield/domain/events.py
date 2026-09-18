"""The telemetry envelope.

EventBridge-shaped from day one (`DESIGN.md` section 9.1). This is the
"adopt the model, abstract the transport" principle: moving to EventBridge
changes where the envelope goes, never what it looks like.

The envelope is hand-written and stable. The 18 `payload` shapes are generated
from `packages/contracts/events.schema.json` -- see `docs/DECISIONS-RESOLVED.md`
C1 and C7.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EventDetail(BaseModel):
    """The EventBridge `detail` block: everything AgentShield-specific."""

    run_id: str
    seq: int = Field(ge=0)
    """Monotonic per-run counter assigned by the emitter.

    This is the cursor for the Live Feed, the ordering key for replay, and the
    dedup key for the WebSocket. Order by `seq` everywhere -- `sim_ts` is for
    display only, and wall time is for nothing.
    """

    sim_ts: int
    employee_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    """One governed event. Nothing reaches storage or the bus except through
    `telemetry/emitter.py`, which is the only constructor of this type.
    """

    id: str
    source: str
    """`agentshield.sim` or `agentshield.live`.

    Telemetry attribution only. A policy cannot read it (see
    `domain.enums.Source`), so the two modes cannot diverge.
    """

    detail_type: str
    time: str
    detail: EventDetail


class GroundTruthRecord(BaseModel):
    """The label the detector is not allowed to see.

    Written by the emitter to `PK=RUN#<id>, SK=GT#<seq>` -- a key prefix
    `RiskScopedDocStore` raises on. Read by exactly one file in the repository:
    `infra/scripts/evaluate.py`.
    """

    run_id: str
    seq: int
    employee_id: str
    scenario_profile: str
    stage: str | None = None
    note: str | None = None
