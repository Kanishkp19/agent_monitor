"""The WebSocket stream.

One socket per browser tab, carrying the governed event stream. Three details
matter:

**`since` is a sequence cursor, not a timestamp.** A client reconnects with
the last `seq` it saw and gets exactly what it missed. Timestamps would
double-deliver or skip under clock skew.

**Coalescing is speed-aware.** At 1x every event is its own frame. At 10x the
server batches into 250 ms groups, because a browser cannot usefully render
two hundred frames a second and trying is what floods the tab.

**A large gap triggers a resnapshot, not a catch-up.** Past 500 events the
client refetches `/sim/runs/{id}/state` rather than replaying, because
replaying half a minute of history into an animated canvas is a lie about
what happened.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from agentshield.deps import get_services

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_SECONDS = 15
GAP_RESNAPSHOT_THRESHOLD = 500


@router.websocket("/ws/stream")
async def stream(
    websocket: WebSocket,
    run_id: str = Query(...),
    since: int = Query(0),
) -> None:
    services = get_services()
    await websocket.accept()
    services.hub.add(websocket)

    try:
        await _replay_gap(websocket, services, run_id, since)

        heartbeat = asyncio.create_task(_heartbeat(websocket))
        try:
            while True:
                # The client sends nothing but pings; this keeps the socket
                # alive and surfaces a disconnect promptly.
                await websocket.receive_text()
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.debug("websocket closed", exc_info=True)
    finally:
        services.hub.remove(websocket)


async def _replay_gap(websocket: WebSocket, services, run_id: str, since: int) -> None:  # type: ignore[no-untyped-def]
    """Deliver what the client missed, or tell it to resnapshot."""
    current = await services.emitter.current_seq(run_id)
    gap = current - since

    if since and gap > GAP_RESNAPSHOT_THRESHOLD:
        await websocket.send_json(
            {
                "kind": "snapshot",
                "seq": current,
                "reason": "gap_too_large",
                "gap": gap,
            }
        )
        return

    if gap <= 0:
        return

    events = await services.emitter.read_page(run_id, since_seq=since, limit=500)
    if events:
        await websocket.send_json(
            {
                "kind": "batch",
                "seq": events[-1].detail.seq,
                "events": [e.model_dump(mode="json") for e in events],
            }
        )


async def _heartbeat(websocket: WebSocket) -> None:
    """Every 15 seconds.

    Without it an idle simulation looks identical to a dead socket, and the
    client's connection dot would go amber during a pause.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await websocket.send_json({"kind": "heartbeat", "seq": 0})
        except Exception:
            return
