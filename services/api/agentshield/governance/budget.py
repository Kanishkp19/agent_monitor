"""Spend guards.

Budgets are enforced inside AgentShield, not at the provider -- the provider
finds out about a runaway session when the invoice arrives, which is three
weeks too late to be a control.

The check is deliberately *pre-flight*: estimated cost is added to today's
spend and compared against the cap before the model is called. A request that
would cross the line is blocked rather than truncated, and the block names the
number, so the answer to "why?" is a figure rather than a policy id.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentshield.domain.models import ActorContext
from agentshield.telemetry.counters import Counters


@dataclass(frozen=True)
class BudgetVerdict:
    ok: bool
    scope: str
    budget_usd: float
    spend_usd: float
    projected_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.budget_usd - self.spend_usd)

    @property
    def message(self) -> str:
        if self.ok:
            return ""
        return (
            f"This request would take {self.scope} spend to "
            f"${self.projected_usd:.2f}, over the ${self.budget_usd:.2f} daily cap."
        )


# A team's cap is the sum of its members' caps times this. Teams routinely
# have one person having a heavy day while others idle; a hard sum would make
# the team cap bind before any individual one ever did, which would train
# people to ignore it.
TEAM_BUDGET_MULTIPLIER = 0.8


class BudgetGuard:
    def __init__(self, counters: Counters) -> None:
        self._counters = counters

    async def check(
        self,
        *,
        run_id: str,
        actor: ActorContext,
        sim_date: str,
        est_cost_usd: float,
        team_budget_usd: float | None = None,
    ) -> BudgetVerdict:
        """Would this request cross a cap? Employee first, then team."""
        employee = await self._counters.read(run_id, "emp", actor.id, sim_date)
        spend = float(employee.get("cost_usd", actor.spend_today_usd))
        projected = spend + est_cost_usd

        if projected > actor.daily_budget_usd:
            return BudgetVerdict(
                ok=False,
                scope="employee",
                budget_usd=actor.daily_budget_usd,
                spend_usd=spend,
                projected_usd=projected,
            )

        if team_budget_usd is not None:
            team = await self._counters.read(run_id, "team", actor.team, sim_date)
            team_spend = float(team.get("cost_usd", 0.0))
            team_projected = team_spend + est_cost_usd
            cap = team_budget_usd * TEAM_BUDGET_MULTIPLIER
            if team_projected > cap:
                return BudgetVerdict(
                    ok=False,
                    scope="team",
                    budget_usd=cap,
                    spend_usd=team_spend,
                    projected_usd=team_projected,
                )

        return BudgetVerdict(
            ok=True,
            scope="employee",
            budget_usd=actor.daily_budget_usd,
            spend_usd=spend,
            projected_usd=projected,
        )
