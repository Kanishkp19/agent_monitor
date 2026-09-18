"""BlobStorePort -- the only home for raw prompts.

Holds raw prompts (`raw/{task_id}/prompt.json`), redaction originals, exported
datasets and model payload archives. A raw secret value lives here and nowhere
else: never in an event payload, never in a log line, never on the wire to the
frontend.

Every read of a `raw/` key emits `audit.raw_access`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BlobStorePort(Protocol):
    async def put_object(self, key: str, data: bytes, content_type: str) -> str:
        """Store bytes and return the canonical key."""
        ...

    async def get_object(self, key: str) -> bytes: ...

    async def presign_get(self, key: str, ttl_seconds: int = 900) -> str: ...
