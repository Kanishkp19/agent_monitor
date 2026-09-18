"""Shared plumbing for the CLI scripts.

Each script is a thin wrapper around the same object graph the API uses --
never a parallel implementation. A script that seeded differently from
`POST /sim/runs` would be a second source of truth about what a run is.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from agentshield.container import get_container
from agentshield.deps import Services, get_services


async def with_services(fn: Callable[[Services], Awaitable[Any]]) -> Any:
    """Open the container, run `fn`, close cleanly."""
    container = get_container()
    await container.startup()
    services = get_services()
    try:
        return await fn(services)
    finally:
        await container.shutdown()


def run(fn: Callable[[Services], Awaitable[Any]]) -> Any:
    return asyncio.run(with_services(fn))


async def latest_run_id(services: Services) -> str | None:
    runs = await services.seeder.recent_runs(limit=1)
    return runs[0].id if runs else None


async def resolve_run(services: Services, run_id: str | None) -> str:
    resolved = run_id or await latest_run_id(services)
    if not resolved:
        raise SystemExit("No runs found. Run `python tasks.py seed` first.")
    return resolved


def heading(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")
