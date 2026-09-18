"""Policy CRUD, validation, and the Policy Lab.

Policies are versioned and append-only: a PATCH creates version N+1 and the
old version stays. That is not bookkeeping -- the Policy Lab replays against
recorded telemetry, and a decision made under v2 can only be explained if v2
still exists.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends

from agentshield.api.schemas import (
    PolicyCreate,
    PolicyLabRequest,
    PolicyPatch,
    PolicyToggle,
    PolicyValidateRequest,
    ok,
)
from agentshield.deps import Services, get_services
from agentshield.domain.enums import Gate
from agentshield.domain.models import Policy
from agentshield.governance import dsl

router = APIRouter(prefix="/policies", tags=["policies"])
lab_router = APIRouter(prefix="/policy-lab", tags=["policy-lab"])


@router.get("")
async def list_policies(
    gate: int | None = None,
    enabled: bool | None = None,
    include_drafts: bool = False,
    run_id: str | None = None,
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    policies = await services.policies.list_all(gate=gate, include_drafts=include_drafts)
    if enabled is not None:
        policies = [p for p in policies if p.enabled == enabled]

    counts = await _match_counts_24h(services, run_id) if run_id else {}

    return ok(
        [{**p.model_dump(mode="json"), "match_count_24h": counts.get(p.id, 0)} for p in policies]
    )


@router.post("", status_code=201)
async def create_policy(
    body: PolicyCreate, services: Services = Depends(get_services)
) -> dict[str, Any]:
    policy = Policy(
        id=_slug(body.name),
        version=1,
        name=body.name,
        gate=Gate(body.gate),
        priority=body.priority,
        effect=body.effect,  # type: ignore[arg-type]
        enabled=body.enabled,
        is_draft=body.is_draft,
        when=body.when,
        approver=body.approver,
        ttl_sim_seconds=body.ttl_sim_seconds,
        route_override=body.route_override,
        message=body.message,
        created_at=datetime.now(UTC).isoformat(),
        created_by="operator",
    )
    saved = await services.policies.save(policy)
    return ok(saved.model_dump(mode="json"))


@router.patch("/{policy_id}")
async def patch_policy(
    policy_id: str, body: PolicyPatch, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Creates version N+1 and repoints CURRENT."""
    patch = body.model_dump(exclude_none=True)
    if "when" in patch:
        current = await services.policies.get(policy_id)
        dsl.validate_or_raise(patch["when"], current.gate)
    updated = await services.policies.update(policy_id, patch)
    return ok(updated.model_dump(mode="json"))


@router.post("/{policy_id}/toggle")
async def toggle_policy(
    policy_id: str, body: PolicyToggle, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Takes effect on the next evaluation. No restart."""
    policy = await services.policies.toggle(policy_id, body.enabled)
    return ok(policy.model_dump(mode="json"))


@router.get("/{policy_id}/versions")
async def policy_versions(
    policy_id: str, services: Services = Depends(get_services)
) -> dict[str, Any]:
    versions = await services.policies.versions(policy_id)
    return ok([v.model_dump(mode="json") for v in versions])


@router.post("/validate")
async def validate_policy(body: PolicyValidateRequest) -> dict[str, Any]:
    """Dry-run the DSL without saving.

    Called by the editor, debounced. Returns the fields the condition reads,
    which is how the editor offers autocomplete that cannot suggest a field
    the gate would reject.
    """
    dsl.validate_or_raise(body.when, body.gate)
    return ok({"valid": True, "fields_used": dsl.fields_used(body.when)})


@router.get("/fields")
async def policy_fields() -> dict[str, Any]:
    """The field allowlist per gate, for editor autocomplete.

    `source` appears in neither list, deliberately -- see `docs/DESIGN.md`
    section 4.
    """
    return ok(
        {
            "gate1": sorted(dsl.FIELDS_GATE1),
            "gate2": sorted(dsl.FIELDS_GATE2),
            "operators": sorted(dsl.OPS),
            "combinators": sorted(dsl.COMBINATORS),
        }
    )


# ──────────────────────────────────────────────────────────────────────
# Policy Lab
# ──────────────────────────────────────────────────────────────────────


@lab_router.post("/simulate")
async def simulate_policy(
    body: PolicyLabRequest, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """Replay a draft against recorded telemetry.

    Possible only because every decision event stores the full context it was
    evaluated against (decision D8). That is a deliberate ~2 KB per decision,
    paid for this feature and for audit.
    """
    from agentshield.telemetry.replay import PolicyLab

    draft = Policy(
        id="pol_draft_preview",
        version=1,
        name=body.draft_policy.name,
        gate=Gate(body.draft_policy.gate),
        priority=body.draft_policy.priority,
        effect=body.draft_policy.effect,  # type: ignore[arg-type]
        enabled=True,
        is_draft=True,
        when=body.draft_policy.when,
        approver=body.draft_policy.approver,
        ttl_sim_seconds=body.draft_policy.ttl_sim_seconds,
        route_override=body.draft_policy.route_override,
        message=body.draft_policy.message,
    )

    lab = PolicyLab(docstore=services.container.docstore, policies=services.policies)
    result = await lab.simulate(
        run_id=body.run_id, draft=draft, window_sim_hours=body.window_sim_hours
    )
    return ok(result)


@lab_router.post("/promote", status_code=201)
async def promote_policy(
    body: PolicyCreate, services: Services = Depends(get_services)
) -> dict[str, Any]:
    """One click from draft to enabled, as a new policy version."""
    policy = Policy(
        id=_slug(body.name),
        version=1,
        name=body.name,
        gate=Gate(body.gate),
        priority=body.priority,
        effect=body.effect,  # type: ignore[arg-type]
        enabled=True,
        is_draft=False,
        when=body.when,
        approver=body.approver,
        ttl_sim_seconds=body.ttl_sim_seconds,
        route_override=body.route_override,
        message=body.message,
        created_at=datetime.now(UTC).isoformat(),
        created_by="policy-lab",
    )
    saved = await services.policies.save(policy)
    return ok(saved.model_dump(mode="json"))


async def _match_counts_24h(services: Services, run_id: str) -> dict[str, int]:
    """How often each policy actually fired.

    A policy list without this is a list of intentions. The one that has
    matched zero times in a day is either dead weight or a control that is
    not working, and both are worth knowing.
    """
    counts: dict[str, int] = {}
    for detail_type in ("gate1.decision", "gate2.decision"):
        events = await services.emitter.read_page(run_id, detail_type=detail_type, limit=500)
        for event in events:
            for match in event.detail.payload.get("matched_policies", []) or []:
                policy_id = match.get("policy_id")
                if policy_id:
                    counts[policy_id] = counts.get(policy_id, 0) + 1
    return counts


def _slug(name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in name.lower())
    return f"pol_{cleaned.strip('_')[:48]}"
