"""Decision precedence. Fixed, and never configurable.

    block > review > redact > allow

Making this configurable would be a mistake with a long tail: an operator who
can reorder it can, with one edit, turn every block in the system into an
allow, and nothing about the policy list would look different afterwards.

Within the same effect, higher `priority` wins for *attribution* only -- it
decides which policy gets named in the trace and in the message shown to the
requester. The decision itself is unchanged.
"""

from __future__ import annotations

from agentshield.domain.enums import Decision
from agentshield.domain.models import PolicyMatch

# Index = strength. Compared by position, never by name.
PRECEDENCE: tuple[Decision, ...] = (
    Decision.ALLOW,
    Decision.REDACT,
    Decision.REVIEW,
    Decision.BLOCK,
)

_RANK: dict[Decision, int] = {d: i for i, d in enumerate(PRECEDENCE)}


def rank(decision: Decision) -> int:
    return _RANK[decision]


def strongest(decisions: list[Decision]) -> Decision:
    return max(decisions, key=rank) if decisions else Decision.ALLOW


def resolve(matches: list[PolicyMatch]) -> tuple[Decision, PolicyMatch | None]:
    """The winning decision, and the policy credited with it.

    Returns `(ALLOW, None)` when nothing matched -- the absence of a policy is
    not itself a decision, and the caller distinguishes "allowed because no
    rule applied" from "allowed because a rule said so".
    """
    if not matches:
        return Decision.ALLOW, None

    winning = strongest([m.effect for m in matches])
    candidates = [m for m in matches if m.effect == winning]
    # Highest priority wins attribution; ties break on policy id so the trace
    # is stable across runs. An unstable trace is an unreproducible demo.
    attributed = max(candidates, key=lambda m: (m.priority, m.policy_id))
    return winning, attributed


def sort_for_trace(matches: list[PolicyMatch]) -> list[PolicyMatch]:
    """Strongest first, then highest priority. The order shown in the UI."""
    return sorted(matches, key=lambda m: (-rank(m.effect), -m.priority, m.policy_id))
