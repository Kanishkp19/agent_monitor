"""SecretsPort -- named secret lookup.

`.env` locally, Secrets Manager on AWS. Ingest tokens move here for a real
deployment (see the deployment checklist in `docs/06-IMPLEMENTATION-PLAN.md`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SecretsPort(Protocol):
    async def get(self, name: str) -> str: ...
