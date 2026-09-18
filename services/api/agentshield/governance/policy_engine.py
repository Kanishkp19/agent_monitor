"""Policy storage, caching and matching.

Evaluation is a linear scan over the enabled set for a gate. With around
twenty policies and a 50 ms budget this is nowhere near the limit, and it
keeps the decision trace trivially explainable -- the trace *is* the loop.
If it ever matters, index by `(gate, tool)` first; do not reach for a rules
engine, which would trade the one property this design is built on.

Caching is by `(gate, version_hash)` and invalidated **on write only**.
Invalidating per call is the documented cause of gate latency spikes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from agentshield.domain.enums import Decision, Gate
from agentshield.domain.errors import NotFound
from agentshield.domain.models import Policy, PolicyMatch
from agentshield.governance import dsl
from agentshield.ports.docstore import DocItem, DocStorePort

logger = logging.getLogger(__name__)


class PolicyEngine:
    def __init__(self, docstore: DocStorePort) -> None:
        self._docstore = docstore
        self._cache: dict[int, list[Policy]] = {}
        self._version_hash: dict[int, str] = {}

    # ── matching ─────────────────────────────────────────────────────

    async def match(self, gate: Gate | int, context: dict[str, Any]) -> list[PolicyMatch]:
        """Every enabled policy whose condition holds.

        Drafts are excluded here, not filtered later. `is_draft=true` means
        "never evaluated by a live gate" -- the Policy Lab evaluates drafts
        explicitly, against recorded telemetry, and nowhere else.
        """
        policies = await self.active(gate)
        matches: list[PolicyMatch] = []

        for policy in policies:
            try:
                if dsl.evaluate(policy.when, context):
                    matches.append(
                        PolicyMatch(
                            policy_id=policy.id,
                            version=policy.version,
                            effect=policy.effect,
                            priority=policy.priority,
                        )
                    )
            except Exception:
                # One malformed policy degrades that policy, never the gate.
                # It is logged loudly because a policy that cannot evaluate is
                # a control the operator believes they have and does not.
                logger.exception("policy evaluation failed", extra={"policy_id": policy.id})

        return matches

    async def match_with_draft(
        self, gate: Gate | int, context: dict[str, Any], draft: Policy
    ) -> list[PolicyMatch]:
        """Live policies plus one draft. Used only by the Policy Lab."""
        matches = await self.match(gate, context)
        if dsl.evaluate(draft.when, context):
            matches.append(
                PolicyMatch(
                    policy_id=draft.id,
                    version=draft.version,
                    effect=draft.effect,
                    priority=draft.priority,
                )
            )
        return matches

    async def active(self, gate: Gate | int) -> list[Policy]:
        gate_num = int(gate)
        if gate_num in self._cache:
            return self._cache[gate_num]

        page = await self._docstore.query(pk=f"POLICIES#{gate_num}", index="gsi1", limit=500)
        policies = [Policy.model_validate(item.body) for item in page.items]
        enabled = [p for p in policies if p.enabled and not p.is_draft]
        # Highest priority first, so the trace reads in the order an operator
        # would reason about it.
        enabled.sort(key=lambda p: (-p.priority, p.id))

        self._cache[gate_num] = enabled
        self._version_hash[gate_num] = _hash_policies(enabled)
        return enabled

    async def get(self, policy_id: str) -> Policy:
        pointer = await self._docstore.get(f"POLICY#{policy_id}", "CURRENT")
        if pointer is None:
            raise NotFound(f"no policy {policy_id!r}")
        return Policy.model_validate(pointer.body)

    async def versions(self, policy_id: str) -> list[Policy]:
        page = await self._docstore.query(
            pk=f"POLICY#{policy_id}", sk_prefix="V#", ascending=False, limit=100
        )
        return [Policy.model_validate(item.body) for item in page.items]

    async def list_all(
        self, *, gate: int | None = None, include_drafts: bool = False
    ) -> list[Policy]:
        policies: list[Policy] = []
        gates = [gate] if gate else [1, 2]
        for g in gates:
            page = await self._docstore.query(pk=f"POLICIES#{g}", index="gsi1", limit=500)
            policies.extend(Policy.model_validate(item.body) for item in page.items)
        if not include_drafts:
            policies = [p for p in policies if not p.is_draft]
        policies.sort(key=lambda p: (-p.priority, p.id))
        return policies

    # ── writes ───────────────────────────────────────────────────────

    async def save(self, policy: Policy) -> Policy:
        """Write a new version and repoint `CURRENT`.

        Policy writes are append-only. Editing creates version N+1 and the old
        version stays -- for audit, and because the Policy Lab replays against
        the version that was live at the time. Rewriting history would make
        every past decision unexplainable.
        """
        dsl.validate_or_raise(policy.when, policy.gate)

        if not policy.created_at:
            policy.created_at = datetime.now(UTC).isoformat()

        version_item = DocItem(
            pk=f"POLICY#{policy.id}",
            sk=f"V#{policy.version:04d}",
            gsi1pk=f"POLICIES#{int(policy.gate)}",
            gsi1sk=f"{policy.priority:03d}#{policy.id}",
            body=policy.model_dump(mode="json"),
        )
        pointer_item = DocItem(
            pk=f"POLICY#{policy.id}",
            sk="CURRENT",
            gsi1pk=f"POLICIES#{int(policy.gate)}",
            gsi1sk=f"{policy.priority:03d}#{policy.id}",
            body=policy.model_dump(mode="json"),
        )
        await self._docstore.batch_put([version_item, pointer_item])
        self.invalidate()
        return policy

    async def update(self, policy_id: str, patch: dict[str, Any]) -> Policy:
        """Create version N+1 from an existing policy."""
        current = await self.get(policy_id)
        merged = current.model_dump()
        merged.update({k: v for k, v in patch.items() if v is not None})
        merged["version"] = current.version + 1
        merged["created_at"] = datetime.now(UTC).isoformat()
        return await self.save(Policy.model_validate(merged))

    async def toggle(self, policy_id: str, enabled: bool) -> Policy:
        """Enable or disable without bumping the version.

        Takes effect on the next evaluation, with no restart -- the cache is
        invalidated here and rebuilt on the next `active()` call.
        """
        current = await self.get(policy_id)
        current.enabled = enabled
        return await self.save(current)

    def cached_policy(self, policy_id: str) -> Policy | None:
        """A loaded policy, by id, without touching the store.

        The gates need a matched policy's `message` and `route_override` while
        resolving a decision. That lookup is on the hot path and must not add
        IO to it -- everything needed is already in the cache that produced
        the match.
        """
        for policies in self._cache.values():
            for policy in policies:
                if policy.id == policy_id:
                    return policy
        return None

    def invalidate(self) -> None:
        self._cache.clear()
        self._version_hash.clear()

    def version_hash(self, gate: Gate | int) -> str:
        return self._version_hash.get(int(gate), "")


def _hash_policies(policies: list[Policy]) -> str:
    payload = json.dumps(
        [[p.id, p.version, p.priority, p.enabled] for p in policies], sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def effect_of(policy: Policy) -> Decision:
    return policy.effect
