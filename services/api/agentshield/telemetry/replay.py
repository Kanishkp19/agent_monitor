"""Policy Lab: replay a draft against recorded telemetry.

Author a rule, run it against the last N hours of real decisions, and see what
it would have done before anyone's work depends on it. The security lead's
complaint in `docs/01-PRD.md` is precise: she cannot pilot a policy without
risking real engineers' work. This is the answer.

Replay is possible only because every decision event stores the full context
it was evaluated against (decision D8). That is ~2 KB per decision, paid
deliberately -- rebuilding a context by joining events would be both slow and
subtly wrong, because the context reflected a moment, not the current state.

The number that matters is `newly_blocked_previously_succeeded`: work that
completed fine and this rule would have stopped. That is the false-positive
proxy, and a rule that scores high on it is a rule that will generate tickets.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agentshield.agent.router import cost_of, route
from agentshield.domain.enums import Decision
from agentshield.domain.models import Policy
from agentshield.governance import dsl, precedence
from agentshield.governance.policy_engine import PolicyEngine
from agentshield.ports.docstore import DocStorePort

logger = logging.getLogger(__name__)

SAMPLE_LIMIT = 10


class PolicyLab:
    def __init__(self, *, docstore: DocStorePort, policies: PolicyEngine) -> None:
        self._docstore = docstore
        self._policies = policies

    async def simulate(
        self, *, run_id: str, draft: Policy, window_sim_hours: int = 24
    ) -> dict[str, Any]:
        started = time.perf_counter()
        decisions = await self._load_decisions(run_id, draft.gate, window_sim_hours)

        affected: list[dict[str, Any]] = []
        newly_blocked_succeeded = 0
        newly_blocked_already = 0
        extra_approvals = 0
        spend_delta = 0.0

        for record in decisions:
            outcome = self._replay_one(record, draft)
            if outcome is None:
                continue

            affected.append(outcome)
            was, would_be = outcome["was"], outcome["would_be"]

            if would_be == str(Decision.BLOCK):
                if was in (str(Decision.ALLOW), str(Decision.REDACT)):
                    # The expensive kind of false positive: this work
                    # completed, and the rule would have stopped it.
                    newly_blocked_succeeded += 1
                else:
                    newly_blocked_already += 1

            if would_be == str(Decision.REVIEW) and was != str(Decision.REVIEW):
                extra_approvals += 1

            spend_delta += outcome.get("cost_delta", 0.0)

        total = len(decisions) or 1
        window_days = max(1.0, window_sim_hours / 24.0)
        baseline_spend = sum(float(d.get("est_cost_usd", 0.0)) for d in decisions) or 1.0

        return {
            "window": {
                "from_seq": decisions[0]["seq"] if decisions else 0,
                "to_seq": decisions[-1]["seq"] if decisions else 0,
                "from_sim_ts": decisions[0]["sim_ts"] if decisions else 0,
                "to_sim_ts": decisions[-1]["sim_ts"] if decisions else 0,
                "sim_hours": window_sim_hours,
            },
            "decisions_replayed": len(decisions),
            "requests_affected": len(affected),
            "requests_affected_pct": round(len(affected) / total * 100, 1),
            "projected_spend_delta_usd": round(spend_delta, 2),
            "projected_savings_pct": round(abs(spend_delta) / baseline_spend * 100, 1),
            "newly_blocked_previously_succeeded": newly_blocked_succeeded,
            "newly_blocked_previously_blocked": newly_blocked_already,
            "extra_approvals_per_day": round(extra_approvals / window_days, 1),
            "affected_by_role": _count_by(affected, "role"),
            "sample_affected": affected[:SAMPLE_LIMIT],
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    # ── loading ──────────────────────────────────────────────────────

    async def _load_decisions(
        self, run_id: str, gate: Any, window_sim_hours: int
    ) -> list[dict[str, Any]]:
        """A23 -- the replay window.

        Reads the decision events for the relevant gate and pulls the stored
        context snapshot off each one.
        """
        detail_type = "gate1.decision" if int(gate) == 1 else "gate2.decision"
        page = await self._docstore.query(
            pk=f"RUN#{run_id}#TYPE#{detail_type}",
            index="gsi1",
            ascending=False,
            limit=5000,
        )

        records: list[dict[str, Any]] = []
        cutoff: int | None = None

        for item in page.items:
            envelope = item.body
            detail = envelope.get("detail", {})
            payload = detail.get("payload", {})
            sim_ts = int(detail.get("sim_ts", 0))

            if cutoff is None:
                cutoff = sim_ts - window_sim_hours * 3600
            if sim_ts < cutoff:
                break

            snapshot = await self._context_snapshot(detail, int(gate))
            if snapshot is None:
                continue

            records.append(
                {
                    "seq": int(detail.get("seq", 0)),
                    "sim_ts": sim_ts,
                    "task_id": detail.get("task_id"),
                    "employee_id": detail.get("employee_id"),
                    "decision": str(payload.get("decision", "allow")),
                    "est_cost_usd": float(payload.get("est_cost_usd", 0.0)),
                    "routed_model": str(payload.get("routed_model", "")),
                    "complexity": snapshot.get("complexity", "standard"),
                    "role": str(snapshot.get("actor", {}).get("role", "")),
                    "tool_or_task_type": str(
                        payload.get("tool") or snapshot.get("task_type") or ""
                    ),
                    "context": snapshot,
                }
            )

        records.reverse()
        return records

    async def _context_snapshot(self, detail: dict[str, Any], gate: int) -> dict[str, Any] | None:
        """The exact context the gate evaluated, from the decision record."""
        task_id = detail.get("task_id")
        if not task_id:
            return None

        if gate == 1:
            item = await self._docstore.get(f"TASK#{task_id}", f"REQ#req_{task_id}")
            return dict(item.body.get("context_snapshot", {})) if item else None

        page = await self._docstore.query(pk=f"TASK#{task_id}", sk_prefix="ACT#", limit=50)
        payload_action_id = detail.get("payload", {}).get("action_id")
        for item in page.items:
            if item.body.get("id") == payload_action_id:
                return dict(item.body.get("context_snapshot", {}))
        return None

    # ── one decision ─────────────────────────────────────────────────

    def _replay_one(self, record: dict[str, Any], draft: Policy) -> dict[str, Any] | None:
        """Re-evaluate one recorded decision with the draft added.

        Returns `None` when the draft would not have changed the outcome --
        which is the common case, and the reason "requests affected" is a
        small number rather than everything.
        """
        context = record["context"]
        view = _policy_view(context, int(draft.gate))

        if not dsl.evaluate(draft.when, view):
            return None

        was = record["decision"]
        draft_effect = draft.effect

        # The draft joins the live set; precedence still decides. A draft
        # `allow` cannot override a live `block`, which is exactly what stops
        # the Policy Lab from suggesting a rule that would quietly disable a
        # control.
        combined = precedence.strongest([Decision(was), draft_effect])
        would_be = str(combined)

        cost_delta = 0.0
        if draft.route_override and int(draft.gate) == 1:
            cost_delta = self._route_saving(record, draft.route_override)
        elif would_be == str(Decision.BLOCK) and was != str(Decision.BLOCK):
            # A blocked request spends nothing.
            cost_delta = -float(record["est_cost_usd"])

        if would_be == was and cost_delta == 0.0:
            return None

        return {
            "task_id": record["task_id"],
            "employee_id": record["employee_id"],
            "role": record["role"],
            "tool_or_task_type": record["tool_or_task_type"],
            "was": was,
            "would_be": would_be,
            "cost_delta": cost_delta,
        }

    def _route_saving(self, record: dict[str, Any], override: str) -> float:
        """What a forced downgrade would have saved on this request.

        Recomputed from `PRICE_TABLE`, the same table the live estimate used,
        so the Policy Lab's savings figure and the cost view cannot drift.
        """
        context = record["context"]
        est_in = int(context.get("est_input_tokens", 0))
        est_out = int(context.get("est_output_tokens", 0))
        if not est_in and not est_out:
            return 0.0

        was_cost = float(record["est_cost_usd"]) or cost_of(record["routed_model"], est_in, est_out)
        new_model = route(record["complexity"], override=override)  # type: ignore[arg-type]
        return round(cost_of(new_model, est_in, est_out) - was_cost, 6)


def _policy_view(snapshot: dict[str, Any], gate: int) -> dict[str, Any]:
    """Rebuild the flat field map from a stored context snapshot.

    Mirrors `RequestContext.policy_view()` / `ActionContext.policy_view()`. If
    those change, this must change with them -- which is why both are short
    and explicit rather than reflective.
    """
    actor = snapshot.get("actor", {})

    if gate == 1:
        findings = snapshot.get("findings", []) or []
        return {
            "actor.role": str(actor.get("role", "")),
            "actor.team": actor.get("team", ""),
            "actor.seniority": actor.get("seniority", "medium"),
            "actor.prod_access": actor.get("prod_access", "none"),
            "actor.risk_score": actor.get("risk_score", 0),
            "actor.spend_today_usd": actor.get("spend_today_usd", 0.0),
            "actor.daily_budget_usd": actor.get("daily_budget_usd", 0.0),
            "actor.sessions_today": actor.get("sessions_today", 0),
            "actor.is_low_confidence": actor.get("is_low_confidence", True),
            "request.task_type": snapshot.get("task_type", ""),
            "request.complexity": snapshot.get("complexity", "standard"),
            "request.repo": snapshot.get("repo", ""),
            "request.environment": str(snapshot.get("environment", "local")),
            "request.prompt_len": snapshot.get("prompt_len", 0),
            "request.requested_model": snapshot.get("requested_model"),
            "request.est_cost_usd": snapshot.get("est_cost_usd", 0.0),
            "request.est_input_tokens": snapshot.get("est_input_tokens", 0),
            "request.routed_model": snapshot.get("routed_model", ""),
            "request.findings_count": len(findings),
            "request.finding_types": [f.get("detector") for f in findings],
            "request.off_hours": snapshot.get("off_hours", False),
        }

    return {
        "actor.role": str(actor.get("role", "")),
        "actor.team": actor.get("team", ""),
        "actor.seniority": actor.get("seniority", "medium"),
        "actor.prod_access": actor.get("prod_access", "none"),
        "actor.risk_score": actor.get("risk_score", 0),
        "actor.is_low_confidence": actor.get("is_low_confidence", True),
        "action.tool": str(snapshot.get("tool", "")),
        "action.environment": str(snapshot.get("environment", "local")),
        "action.target_resource": snapshot.get("target_resource", ""),
        "action.resource_sensitivity": str(snapshot.get("resource_sensitivity", "low")),
        "action.repeat_count_5m": snapshot.get("repeat_count_5m", 0),
        "action.iteration_index": snapshot.get("iteration_index", 0),
        "task.repo": snapshot.get("repo", ""),
        "task.is_repo_in_scope": snapshot.get("is_repo_in_scope", True),
        "task.is_secret_path": snapshot.get("is_secret_path", False),
        "task.is_protected_branch": snapshot.get("is_protected_branch", False),
        "task.is_external_host": snapshot.get("is_external_host", False),
        "task.cost_so_far_usd": snapshot.get("cost_so_far_usd", 0.0),
        "task.blocked_so_far": snapshot.get("blocked_so_far", 0),
        "task.elapsed_sim_s": snapshot.get("elapsed_sim_s", 0),
    }


def _count_by(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field, "")) or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return [
        {field: key, "count": count} for key, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
