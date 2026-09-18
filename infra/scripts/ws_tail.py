#!/usr/bin/env python
"""Tail the WebSocket event stream.

Replaces `websocat` from the docs, which is not installed on a default
Windows machine and would be a fifth external binary to require.

    python infra/scripts/ws_tail.py --run-id run_7f3a
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("pip install websockets  (it is already in requirements.txt)")
    sys.exit(1)


async def tail(url: str, limit: int) -> int:
    seen = 0
    async with websockets.connect(url) as socket:
        print(f"connected: {url}\n")
        while seen < limit:
            frame = json.loads(await socket.recv())
            kind = frame.get("kind")

            if kind == "heartbeat":
                continue
            if kind == "progress":
                print(f"  [progress] {frame.get('progress')}")
                continue
            if kind == "snapshot":
                # The server is telling the client the gap is too large to
                # replay. A real client refetches /sim/runs/{id}/state here.
                print(f"  [snapshot] gap={frame.get('gap')} -- resnapshot required")
                continue

            for event in frame.get("events", []):
                detail = event.get("detail", {})
                payload = detail.get("payload", {})
                resource = payload.get("target_resource") or payload.get("title") or ""
                print(
                    f"  {detail.get('seq', 0):>6}  {event.get('detail_type', ''):<22} "
                    f"{detail.get('employee_id') or '-':<10} "
                    f"{str(payload.get('decision', '')).upper():<7} {resource}"
                )
                seen += 1
                if seen >= limit:
                    break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--since", type=int, default=0)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--host", default="ws://localhost:8000")
    args = parser.parse_args()

    url = f"{args.host}/ws/stream?run_id={args.run_id}&since={args.since}"
    try:
        return asyncio.run(tail(url, args.limit))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
