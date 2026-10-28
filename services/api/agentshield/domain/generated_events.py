"""Event payload models.

GENERATED FROM packages/contracts/events.schema.json -- DO NOT EDIT

Regenerate with `python tasks.py contracts`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyMatch(BaseModel):
    policy_id: str
    version: int
    effect: str
    priority: int


class MaskedFinding(BaseModel):
    detector: str
    masked: str


class RiskFactor(BaseModel):
    feature: str
    value: float
    z: float
    contribution: float = 0.0
    explanation: str


class SimTickPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`sim.tick` -- emitted by sim/engine.py.
    """

    sim_ts: int
    active_sessions: int
    queued_tasks: int


class SimDayCompletedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`sim.day.completed` -- emitted by sim/engine.py.
    """

    sim_day: int
    tasks: int
    events: int
    cost_usd: float
    blocked: int
    approvals: int
    incidents: int


class SimMeetingStartedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`sim.meeting.started` -- emitted by sim/scenarios.py.

    Purely cosmetic. Moves avatars to the meeting room; no governed outcome depends on it.
    """

    meeting_id: str
    attendees: list[str]
    room: str = ""


class SimMeetingEndedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`sim.meeting.ended` -- emitted by sim/scenarios.py.
    """

    meeting_id: str
    attendees: list[str]


class TaskRequestedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`task.requested` -- emitted by sim/engine.py, /ingest/gate1.
    """

    task_id: str
    employee_id: str
    title: str
    task_type: str
    complexity: str
    repo: str
    environment: str
    is_marquee: bool


class Gate1DecisionPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`gate1.decision` -- emitted by the gate1 caller.

    findings carry the masked form only. A raw secret value never appears in an event payload, a log line, or anything sent to the frontend.
    """

    task_id: str
    request_id: str
    decision: str
    reason_code: str
    matched_policies: list[PolicyMatch]
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    est_cost_usd: float = 0.0
    routed_model: str
    findings: list[MaskedFinding] = Field(default_factory=list)
    budget_remaining_usd: float = 0.0
    latency_ms: float


class ModelInvokedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`model.invoked` -- emitted by agent/runner.py.
    """

    task_id: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    iteration: int
    stop_reason: str
    fallback: bool


class ActionRequestedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`action.requested` -- emitted by agent/runner.py.
    """

    task_id: str
    action_id: str
    tool: str
    target_resource: str
    environment: str
    resource_sensitivity: str
    args_digest: str
    iteration: int


class Gate2DecisionPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`gate2.decision` -- emitted by the gate2 caller.
    """

    task_id: str
    action_id: str
    tool: str
    decision: str
    reason_code: str
    matched_policies: list[PolicyMatch]
    target_resource: str
    environment: str
    repeat_count_5m: int = 0
    latency_ms: float


class ApprovalRequestedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`approval.requested` -- emitted by governance/approvals.py.
    """

    approval_id: str
    task_id: str
    action_id: str
    requester_id: str
    approver_role: str = ""
    approver_scope: str = ""
    reason: str
    risk_at_request: int = 0
    cost_so_far_usd: float = 0.0
    expires_sim_ts: int


class ApprovalDecidedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`approval.decided` -- emitted by governance/approvals.py.
    """

    approval_id: str
    task_id: str
    status: str
    approver_id: str = ""
    note: str = ""
    latency_sim_s: int


class SandboxExecutedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`sandbox.executed` -- emitted by sandbox/.
    """

    task_id: str
    action_id: str
    tool: str
    ok: bool
    duration_ms: int
    output_preview: str = ""


class ActionBlockedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`action.blocked` -- emitted by agent/runner.py.
    """

    task_id: str
    action_id: str
    tool: str
    target_resource: str
    policy_id: str = ""
    message: str


class TaskCompletedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`task.completed` -- emitted by agent/runner.py.
    """

    task_id: str
    employee_id: str
    status: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    actions_total: int
    actions_blocked: int
    duration_sim_s: int


class BudgetExceededPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`budget.exceeded` -- emitted by the budget caller.
    """

    employee_id: str
    scope: str
    budget_usd: float
    spend_usd: float
    sim_date: str


class RiskUpdatedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`risk.updated` -- emitted by the risk scoring caller.

    The office applies an anomaly overlay at score >= 70 and clears it below 60. The overlay is not a state: an employee can be visibly working and flagged at the same time, which is the most interesting thing the demo can show.
    """

    employee_id: str
    score: int
    static: int
    behavioural: int
    ml: int
    confidence: str
    top_factors: list[RiskFactor] = Field(default_factory=list)
    delta: int = 0


class IncidentOpenedPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`incident.opened` -- emitted by risk/incidents.py.
    """

    incident_id: str
    employee_id: str
    detector: str
    score: int
    summary: str
    evidence_count: int


class AutopilotStatePayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`autopilot.state` -- emitted by autopilot/runner.py.
    """

    state: str


class AutopilotGatePayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`autopilot.gate` -- emitted by autopilot/runner.py.
    """

    gate: int
    tool: str = ""
    path: str = ""
    decision: str
    reason: str


class AutopilotModelPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`autopilot.model` -- emitted by autopilot/runner.py.
    """

    provider: str
    model_id: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    retry_count: int = 0
    is_mock: bool


class AutopilotActionPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`autopilot.action` -- emitted by autopilot/runner.py.
    """

    tool: str
    args: str = ""
    decision: str
    result: dict[str, Any]


class AutopilotTestPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`autopilot.test` -- emitted by autopilot/runner.py.
    """

    phase: str
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    summary_line: str = ""


class AuditRawAccessPayload(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    """`audit.raw_access` -- emitted by the blob store reader.

    The blob store is the only home for raw prompts, and every read of one is audited. Without this the redaction guarantee is unverifiable.
    """

    task_id: str
    blob_key: str
    actor_id: str
    reason: str = ""


EVENT_PAYLOADS: dict[str, type[BaseModel]] = {
    "sim.tick": SimTickPayload,
    "sim.day.completed": SimDayCompletedPayload,
    "sim.meeting.started": SimMeetingStartedPayload,
    "sim.meeting.ended": SimMeetingEndedPayload,
    "task.requested": TaskRequestedPayload,
    "gate1.decision": Gate1DecisionPayload,
    "model.invoked": ModelInvokedPayload,
    "action.requested": ActionRequestedPayload,
    "gate2.decision": Gate2DecisionPayload,
    "approval.requested": ApprovalRequestedPayload,
    "approval.decided": ApprovalDecidedPayload,
    "sandbox.executed": SandboxExecutedPayload,
    "action.blocked": ActionBlockedPayload,
    "task.completed": TaskCompletedPayload,
    "budget.exceeded": BudgetExceededPayload,
    "risk.updated": RiskUpdatedPayload,
    "incident.opened": IncidentOpenedPayload,
    "autopilot.state": AutopilotStatePayload,
    "autopilot.gate": AutopilotGatePayload,
    "autopilot.model": AutopilotModelPayload,
    "autopilot.action": AutopilotActionPayload,
    "autopilot.test": AutopilotTestPayload,
    "audit.raw_access": AuditRawAccessPayload,
}


# Every known `detail_type`. `/ingest/events` validates against this
# registry rather than a hardcoded count -- see DECISIONS-RESOLVED.md C1.
EVENT_TYPES: frozenset[str] = frozenset(EVENT_PAYLOADS)


# The six the office renderer reacts to. Everything else still reaches
# the Live Feed; the canvas simply ignores it.
OFFICE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "sim.meeting.started",
        "sim.meeting.ended",
        "task.requested",
        "gate1.decision",
        "gate2.decision",
        "approval.requested",
        "approval.decided",
        "task.completed",
        "risk.updated",
    }
)
