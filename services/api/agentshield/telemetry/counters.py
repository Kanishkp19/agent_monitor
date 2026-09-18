"""Aggregates, maintained on write.

Nothing in this product is computed by scanning. `docs/05-BACKEND-SCHEMA.md`
section 4 enumerates six counter families, each incremented atomically as
events are emitted, so "spend by team" is a key lookup rather than a table
scan -- which is the only way it works identically on SQLite and DynamoDB.
"""

from __future__ import annotations

from typing import Any

from agentshield.domain.enums import Decision, TaskStatus
from agentshield.ports.docstore import DocStorePort

# A session's spend counts as waste if it ended in any of these. The
# definition lives here so the exec view and the API can never disagree about
# the number -- `docs/05-BACKEND-SCHEMA.md` section 4 states it verbatim.
WASTE_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.BLOCKED,
        TaskStatus.DENIED,
        TaskStatus.DENIED_TIMEOUT,
        TaskStatus.FAILED,
    }
)


def counter_sk(dimension: str, key: str, sim_date: str) -> str:
    return f"CTR#{dimension}#{key}#{sim_date}"


def run_counter_sk(sim_date: str) -> str:
    return f"CTR#run#{sim_date}"


class Counters:
    """Atomic increments through `DocStorePort.update(patch={"$add": ...})`."""

    def __init__(self, docstore: DocStorePort) -> None:
        self._docstore = docstore

    async def _add(self, run_id: str, sk: str, deltas: dict[str, Any]) -> None:
        if not deltas:
            return
        await self._docstore.update(pk=f"RUN#{run_id}", sk=sk, patch={"$add": deltas})

    async def record_decision(
        self,
        *,
        run_id: str,
        employee_id: str,
        team: str,
        sim_date: str,
        decision: Decision,
        tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """One gate decision, counted against employee, team and run."""
        deltas: dict[str, Any] = {
            "requests": 1,
            "tokens": tokens,
            "cost_usd": cost_usd,
            _DECISION_FIELD[decision]: 1,
        }
        await self._add(run_id, counter_sk("emp", employee_id, sim_date), deltas)
        await self._add(run_id, counter_sk("team", team, sim_date), deltas)
        await self._add(run_id, run_counter_sk(sim_date), deltas)

    async def record_model_call(
        self,
        *,
        run_id: str,
        model_id: str,
        sim_date: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
    ) -> None:
        await self._add(
            run_id,
            counter_sk("model", model_id, sim_date),
            {
                "calls": 1,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
            },
        )

    async def record_tool_attempt(
        self, *, run_id: str, tool: str, sim_date: str, decision: Decision
    ) -> None:
        deltas: dict[str, Any] = {"attempted": 1}
        if decision is Decision.ALLOW:
            deltas["allowed"] = 1
        elif decision is Decision.BLOCK:
            deltas["blocked"] = 1
        elif decision is Decision.REVIEW:
            deltas["review"] = 1
        await self._add(run_id, counter_sk("tool", tool, sim_date), deltas)

    async def record_waste(
        self, *, run_id: str, sim_date: str, cost_usd: float, reason: str
    ) -> None:
        """Spend on a session that produced nothing.

        Counted when a task reaches a terminal status in `WASTE_STATUSES`, or
        when `pol_retry_loop_guard` fires. This is the "waste prevented"
        figure on the exec view.
        """
        await self._add(
            run_id,
            counter_sk("waste", reason, sim_date),
            {"waste_usd": cost_usd, "sessions": 1},
        )
        await self._add(run_id, run_counter_sk(sim_date), {"waste_usd": cost_usd})

    async def read(self, run_id: str, dimension: str, key: str, sim_date: str) -> dict[str, Any]:
        item = await self._docstore.get(f"RUN#{run_id}", counter_sk(dimension, key, sim_date))
        return dict(item.body) if item else {}

    async def read_dimension(self, run_id: str, dimension: str) -> dict[str, dict[str, Any]]:
        """Every counter for a dimension, keyed by `<key>#<sim_date>` (A21)."""
        page = await self._docstore.query(
            pk=f"RUN#{run_id}", sk_prefix=f"CTR#{dimension}#", limit=1000
        )
        out: dict[str, dict[str, Any]] = {}
        for item in page.items:
            out[item.sk.removeprefix(f"CTR#{dimension}#")] = dict(item.body)
        return out


_DECISION_FIELD: dict[Decision, str] = {
    Decision.ALLOW: "allowed",
    Decision.BLOCK: "blocked",
    Decision.REVIEW: "review",
    Decision.REDACT: "redacted",
}
