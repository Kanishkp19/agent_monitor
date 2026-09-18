"""Gate 1 -- request governance.

Runs before any prompt reaches a model. The ten steps from `docs/DESIGN.md`
section 5.2, each a named function so it can be tested on its own and so
`evaluate()` reads as the algorithm rather than as an implementation of it.

Two invariants:

**Pure.** `evaluate()` takes a context and returns a decision. It performs no
persistence and emits no events -- the caller does both. That is what lets the
simulator and `/ingest/gate1` share this code path exactly, and what lets a
unit test construct a gate with no store at all.

**Fails closed.** Any unhandled exception returns `BLOCK` with
`reason_code=gate_error`. A governance system that fails open is worse than
having none, because it produces evidence that it was working.
"""

from __future__ import annotations

import logging
import time

from agentshield.domain.enums import Decision
from agentshield.domain.models import (
    DecisionResult,
    PolicyMatch,
    RequestContext,
)
from agentshield.governance import precedence
from agentshield.governance.budget import BudgetGuard, BudgetVerdict
from agentshield.governance.policy_engine import PolicyEngine
from agentshield.governance.redaction import ScanResult, scan

logger = logging.getLogger(__name__)


class Gate1:
    def __init__(
        self,
        *,
        policies: PolicyEngine,
        budget: BudgetGuard | None = None,
        redaction_enabled: bool = True,
    ) -> None:
        self._policies = policies
        self._budget = budget
        self._redaction_enabled = redaction_enabled

    async def evaluate(
        self,
        context: RequestContext,
        *,
        run_id: str = "",
        sim_date: str = "",
        team_budget_usd: float | None = None,
    ) -> DecisionResult:
        started = time.perf_counter()
        try:
            return await self._evaluate(
                context,
                run_id=run_id,
                sim_date=sim_date,
                team_budget_usd=team_budget_usd,
                started=started,
            )
        except Exception:
            logger.exception("gate1 failed; blocking", extra={"actor": context.actor.id})
            return DecisionResult(
                decision=Decision.BLOCK,
                reason_code="gate_error",
                message="The request could not be evaluated and was blocked.",
                latency_ms=_elapsed_ms(started),
            )

    async def _evaluate(
        self,
        context: RequestContext,
        *,
        run_id: str,
        sim_date: str,
        team_budget_usd: float | None,
        started: float,
    ) -> DecisionResult:
        # 2. Scan the prompt. Done before anything else touches the text, so
        #    no downstream step can persist or log a raw value.
        findings = self._scan(context)
        context.findings = findings.findings

        # 6. Budget. Checked before the call, not after -- the point is to
        #    prevent the spend, not to report it.
        verdict = await self._check_budget(
            context, run_id=run_id, sim_date=sim_date, team_budget_usd=team_budget_usd
        )

        # 8. Policies.
        matches = await self._policies.match(1, context.policy_view())

        # 9. Resolve.
        return self._resolve(context, findings, verdict, matches, started)

    # ── steps ────────────────────────────────────────────────────────

    def _scan(self, context: RequestContext) -> ScanResult:
        return scan(context.prompt_text, enabled=self._redaction_enabled)

    async def _check_budget(
        self,
        context: RequestContext,
        *,
        run_id: str,
        sim_date: str,
        team_budget_usd: float | None,
    ) -> BudgetVerdict:
        if self._budget is None or not run_id:
            return BudgetVerdict(
                ok=True,
                scope="employee",
                budget_usd=context.actor.daily_budget_usd,
                spend_usd=context.actor.spend_today_usd,
                projected_usd=context.actor.spend_today_usd + context.est_cost_usd,
            )
        return await self._budget.check(
            run_id=run_id,
            actor=context.actor,
            sim_date=sim_date,
            est_cost_usd=context.est_cost_usd,
            team_budget_usd=team_budget_usd,
        )

    def _resolve(
        self,
        context: RequestContext,
        findings: ScanResult,
        verdict: BudgetVerdict,
        matches: list[PolicyMatch],
        started: float,
    ) -> DecisionResult:
        """Precedence: budget > block > review > redact > allow.

        Budget sits above the policy set on purpose. A spend cap is not a rule
        an operator can accidentally out-prioritise -- if the money is gone,
        the money is gone.
        """
        ordered = precedence.sort_for_trace(matches)
        route_override = self._route_override(matches)

        if not verdict.ok:
            return DecisionResult(
                decision=Decision.BLOCK,
                reason_code="budget_exceeded",
                matched_policies=ordered,
                message=verdict.message,
                latency_ms=_elapsed_ms(started),
            )

        effect, attributed = precedence.resolve(matches)

        if effect is Decision.BLOCK:
            return DecisionResult(
                decision=Decision.BLOCK,
                reason_code=f"policy:{attributed.policy_id}" if attributed else "policy",
                matched_policies=ordered,
                message=self._message_for(attributed),
                route_override=route_override,
                latency_ms=_elapsed_ms(started),
            )

        if effect is Decision.REVIEW:
            return DecisionResult(
                decision=Decision.REVIEW,
                reason_code=f"policy:{attributed.policy_id}" if attributed else "policy",
                matched_policies=ordered,
                message=self._message_for(attributed),
                route_override=route_override,
                latency_ms=_elapsed_ms(started),
            )

        # A secret in the prompt always redacts, whether or not a policy said
        # so. `pol_redact_secrets` exists to make the behaviour visible in the
        # policy list; the guarantee does not depend on it being enabled.
        if findings.findings:
            return DecisionResult(
                decision=Decision.REDACT,
                reason_code="sensitive_data",
                matched_policies=ordered,
                message=(
                    f"{len(findings.findings)} secret(s) removed from the prompt "
                    "before it reached the model."
                ),
                redacted_text=findings.redacted_text,
                route_override=route_override,
                latency_ms=_elapsed_ms(started),
            )

        return DecisionResult(
            decision=Decision.ALLOW,
            reason_code="clean" if not matches else "policy_allow",
            matched_policies=ordered,
            route_override=route_override,
            latency_ms=_elapsed_ms(started),
        )

    def _route_override(self, matches: list[PolicyMatch]) -> str | None:
        """A matched `allow` policy may force a cheaper model.

        This is the "interns may not use frontier models for trivial work"
        rule -- it does not block anyone, it just costs less, which is why it
        is the Policy Lab's showcase draft.
        """
        for match in sorted(matches, key=lambda m: -m.priority):
            if match.effect is Decision.ALLOW:
                policy = self._policies.cached_policy(match.policy_id)
                if policy and policy.route_override:
                    return policy.route_override
        return None

    def _message_for(self, match: PolicyMatch | None) -> str | None:
        if match is None:
            return None
        policy = self._policies.cached_policy(match.policy_id)
        return policy.message if policy else None


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0
