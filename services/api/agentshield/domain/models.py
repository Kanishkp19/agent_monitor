"""Every domain model in AgentShield.

From `docs/02-TRD.md` sections 3.2 and 3.3. Two rules govern this file:

  * `EmployeePublic` has no `scenario_profile` field **at the type level**.
    Not a serialiser flag that can be forgotten -- the field does not exist,
    so no API response can leak which employee the simulator made adversarial.
  * `RequestContext` and `ActionContext` carry everything a gate needs and
    nothing about where they came from. The only field that differs between
    modes is `source`, which is telemetry metadata and is forbidden from
    appearing in any policy condition.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentshield.domain.enums import (
    TERMINAL_TASK_STATUSES,
    ApprovalStatus,
    Archetype,
    Decision,
    Environment,
    Gate,
    Role,
    ScenarioProfile,
    Sensitivity,
    Source,
    TaskStatus,
    ToolName,
)
from agentshield.domain.errors import IllegalTransition

Complexity = Literal["trivial", "standard", "complex"]
Seniority = Literal["low", "medium", "high"]
ProdAccess = Literal["none", "review", "allow"]
TokenNorm = Literal["very_low", "low", "medium", "high"]
AgentBrand = Literal["claude_code", "codex", "internal", "mcp"]
Confidence = Literal["low", "normal"]

TaskType = Literal[
    "bug_fix",
    "unit_test",
    "documentation",
    "api_work",
    "data_access",
    "deployment",
    "refactor",
    "incident_response",
]


# ──────────────────────────────────────────────────────────────────────
# People
# ──────────────────────────────────────────────────────────────────────


class Persona(BaseModel):
    """The behavioural template an employee is instantiated from.

    Six archetypes, seeded jitter, twenty employees. Behaviour comes from here
    and from the task generator -- never from twenty continuous LLM loops,
    which fail on cost, latency, determinism and debuggability alike.
    """

    archetype: Archetype
    role: Role
    team: str
    experience: Seniority
    work_hours: tuple[int, int] = (9, 18)
    allowed_repositories: list[str] = Field(default_factory=list)
    normal_task_types: list[TaskType] = Field(default_factory=list)
    prod_access: ProdAccess = "none"
    token_usage_norm: TokenNorm = "medium"
    daily_budget_usd: float = 20.0
    mistake_probability: float = Field(0.04, ge=0.0, le=1.0)
    high_risk_request_probability: float = Field(0.01, ge=0.0, le=1.0)
    llm_invocation_rate: float = Field(0.08, ge=0.0, le=1.0)


class EmployeeDailyCounters(BaseModel):
    requests: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    allowed: int = 0
    blocked: int = 0
    review: int = 0
    redacted: int = 0


class Employee(BaseModel):
    """The full internal record. Never serialised to a client."""

    id: str
    run_id: str
    name: str
    role: Role
    team: str
    agent_brand: AgentBrand
    persona: Persona
    sprite_key: str
    desk: tuple[int, int]
    desk_slot: str = ""
    manager_id: str | None = None

    # ── simulation-internal ──────────────────────────────────────────
    # Read by `sim/`. Written to a ground-truth key the risk engine has no
    # query path to. Absent from `EmployeePublic` by construction.
    scenario_profile: ScenarioProfile = ScenarioProfile.NORMAL
    scenario_day_offset: int = 0

    def to_public(
        self,
        *,
        status: TaskStatus = TaskStatus.QUEUED,
        current_task_id: str | None = None,
        risk_score: int = 0,
        risk_confidence: Confidence = "low",
        today: EmployeeDailyCounters | None = None,
    ) -> EmployeePublic:
        """The only way an employee reaches an API response."""
        return EmployeePublic(
            id=self.id,
            name=self.name,
            role=self.role,
            team=self.team,
            agent_brand=self.agent_brand,
            sprite_key=self.sprite_key,
            desk=self.desk,
            desk_slot=self.desk_slot,
            manager_id=self.manager_id,
            daily_budget_usd=self.persona.daily_budget_usd,
            status=status,
            current_task_id=current_task_id,
            risk_score=risk_score,
            risk_confidence=risk_confidence,
            today=today or EmployeeDailyCounters(),
        )


class EmployeePublic(BaseModel):
    """What the API is allowed to return.

    `scenario_profile` is absent by construction. The operator sees only what
    the system inferred from telemetry -- which is the entire point of the
    hidden-actor exercise.
    """

    id: str
    name: str
    role: Role
    team: str
    agent_brand: str
    sprite_key: str
    desk: tuple[int, int]
    desk_slot: str = ""
    manager_id: str | None = None
    daily_budget_usd: float
    status: TaskStatus
    current_task_id: str | None = None
    risk_score: int = Field(0, ge=0, le=100)
    risk_confidence: Confidence = "low"
    today: EmployeeDailyCounters = Field(default_factory=EmployeeDailyCounters)


# ──────────────────────────────────────────────────────────────────────
# Work
# ──────────────────────────────────────────────────────────────────────


class Task(BaseModel):
    id: str
    run_id: str
    employee_id: str
    title: str
    task_type: TaskType
    complexity: Complexity
    repo: str
    environment: Environment
    status: TaskStatus = TaskStatus.QUEUED
    routed_model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    risk_at_request: int = 0
    is_marquee: bool = False
    started_sim_ts: int = 0
    ended_sim_ts: int | None = None
    source: Source = Source.SIM

    # Session accounting, used by Gate 2's context and the feature vector.
    actions_total: int = 0
    actions_blocked: int = 0
    actions_review: int = 0
    prompt_text: str = ""
    session_grants: list[str] = Field(default_factory=list)
    """Tuples auto-allowed for the rest of this task by `approve_session`.

    Format `tool|resource|environment`. Scoped to the task deliberately: a
    session grant that outlived its task would be a standing permission
    nobody remembers granting.
    """

    def transition_to(self, status: TaskStatus) -> None:
        """Move to a new status, or raise.

        An illegal transition is a bug in the caller and is never silently
        corrected -- a task whose history quietly repaired itself cannot be
        used as evidence, and evidence is the product.
        """
        if self.status == status:
            return
        if self.status in TERMINAL_TASK_STATUSES:
            raise IllegalTransition(
                f"task {self.id} is terminal ({self.status}); cannot become {status}"
            )
        allowed = _TASK_TRANSITIONS.get(self.status, frozenset())
        if status not in allowed:
            raise IllegalTransition(
                f"task {self.id}: {self.status} -> {status} is not a legal transition"
            )
        self.status = status


# The state machine from `docs/05-BACKEND-SCHEMA.md` section 8.
_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.REQUESTING, TaskStatus.FAILED}),
    TaskStatus.REQUESTING: frozenset(
        {
            TaskStatus.WORKING,
            TaskStatus.BLOCKED,
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.AWAITING_APPROVAL: frozenset(
        {
            TaskStatus.WORKING,
            TaskStatus.DENIED,
            TaskStatus.DENIED_TIMEOUT,
            TaskStatus.FAILED,
        }
    ),
    TaskStatus.WORKING: frozenset(
        {
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.BLOCKED,
        }
    ),
}


class SensitiveFinding(BaseModel):
    detector: str
    masked: str
    offset: int
    length: int


class ToolResult(BaseModel):
    ok: bool
    output: str = ""
    error: str | None = None
    duration_ms: int = 0


class PolicyMatch(BaseModel):
    policy_id: str
    version: int
    effect: Decision
    priority: int


class GateRequest(BaseModel):
    """The Gate 1 record, persisted under the task."""

    id: str
    task_id: str
    run_id: str
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    est_cost_usd: float = 0.0
    routed_model: str = ""
    findings: list[SensitiveFinding] = Field(default_factory=list)
    decision: Decision = Decision.ALLOW
    reason_code: str = "clean"
    matched_policies: list[PolicyMatch] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    """The full evaluated context.

    Stored on every decision so the Policy Lab can replay without rebuilding
    by join, and so an audit shows exactly what the gate saw. Roughly 2 KB per
    decision, paid deliberately (decision D8).
    """

    latency_ms: float = 0.0
    sim_ts: int = 0


class AgentAction(BaseModel):
    """The Gate 2 record, one per attempted tool call."""

    id: str
    task_id: str
    run_id: str
    seq: int
    tool: ToolName
    args: dict[str, Any] = Field(default_factory=dict)
    args_digest: str = ""
    target_resource: str = ""
    resource_sensitivity: Sensitivity = Sensitivity.LOW
    environment: Environment = Environment.LOCAL
    decision: Decision = Decision.ALLOW
    reason_code: str = "clean"
    matched_policies: list[PolicyMatch] = Field(default_factory=list)
    approval_id: str | None = None
    result: ToolResult | None = None
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0
    sim_ts: int = 0


# ──────────────────────────────────────────────────────────────────────
# Policy
# ──────────────────────────────────────────────────────────────────────


class ApproverSpec(BaseModel):
    role: Role
    scope: Literal["team", "org"] = "team"


class Policy(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    id: str
    version: int = 1
    name: str
    gate: Gate
    priority: int = Field(50, ge=0, le=999)
    effect: Decision
    enabled: bool = True
    is_draft: bool = False
    when: dict[str, Any] = Field(default_factory=dict)
    approver: ApproverSpec | None = None
    ttl_sim_seconds: int = Field(300, ge=30, le=86_400)
    route_override: str | None = None
    message: str = ""
    created_at: str = ""
    created_by: str = "system"


class Approval(BaseModel):
    id: str
    run_id: str
    task_id: str
    action_id: str
    requester_id: str
    approver_id: str | None = None
    approver_role: Role | None = None
    approver_scope: Literal["team", "org"] = "team"
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: str = ""
    policy_id: str = ""
    tool: ToolName | None = None
    target_resource: str = ""
    environment: Environment = Environment.LOCAL
    args_preview: str = ""
    risk_at_request: int = 0
    cost_so_far_usd: float = 0.0
    requested_sim_ts: int = 0
    decided_sim_ts: int | None = None
    expires_sim_ts: int = 0
    note: str | None = None

    @property
    def grant_key(self) -> str:
        """The tuple `approve_session` grants for the rest of the task."""
        return f"{self.tool}|{self.target_resource}|{self.environment}"


# ──────────────────────────────────────────────────────────────────────
# Risk
# ──────────────────────────────────────────────────────────────────────


class RiskFactor(BaseModel):
    feature: str
    value: float
    z: float
    contribution: float = Field(0.0, ge=0.0, le=1.0)
    explanation: str
    """Plain language, written by `risk/scoring.py`.

    The wording lives there and nowhere else, so the API, the employee drawer
    and `/control/risk` can never disagree about why someone is flagged.
    """


class RiskProfile(BaseModel):
    employee_id: str
    run_id: str
    score: int = Field(0, ge=0, le=100)
    static: int = 0
    behavioural: int = 0
    ml: int = 0
    confidence: Confidence = "low"
    top_factors: list[RiskFactor] = Field(default_factory=list)
    features: dict[str, float] = Field(default_factory=dict)
    sessions_observed: int = 0
    updated_sim_ts: int = 0


class IncidentEvidence(BaseModel):
    event_seq: int
    sim_ts: int
    kind: str
    detail: str


class Incident(BaseModel):
    id: str
    run_id: str
    employee_id: str
    detector: Literal["composite", "static_critical", "isolation_forest"]
    score: int = 0
    opened_sim_ts: int = 0
    last_seen_sim_ts: int = 0
    status: Literal["open", "acknowledged", "closed"] = "open"
    evidence: list[IncidentEvidence] = Field(default_factory=list)
    summary: str = ""


# ──────────────────────────────────────────────────────────────────────
# Gate contexts -- the mode-parity boundary
# ──────────────────────────────────────────────────────────────────────


class ActorContext(BaseModel):
    """Who is asking. Identical whether the caller is the simulator or a real
    agent over HTTP -- and in Live Mode the role comes from the registered
    identity behind the bearer token, never from the request body.
    """

    id: str
    role: Role
    team: str
    seniority: Seniority = "medium"
    allowed_repositories: list[str] = Field(default_factory=list)
    prod_access: ProdAccess = "none"
    work_hours: tuple[int, int] = (9, 18)
    daily_budget_usd: float = 20.0
    spend_today_usd: float = 0.0
    risk_score: int = 0
    sessions_today: int = 0
    is_low_confidence: bool = True


class RequestContext(BaseModel):
    """Everything Gate 1 needs, and nothing about where it came from."""

    source: Source = Source.SIM
    actor: ActorContext
    task_id: str = ""
    task_type: TaskType = "bug_fix"
    complexity: Complexity = "standard"
    repo: str = ""
    environment: Environment = Environment.LOCAL
    prompt_text: str = ""
    prompt_len: int = 0
    requested_model: str | None = None
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    est_cost_usd: float = 0.0
    routed_model: str = ""
    findings: list[SensitiveFinding] = Field(default_factory=list)
    off_hours: bool = False
    sim_ts: int = 0

    def policy_view(self) -> dict[str, Any]:
        """The flat field map the DSL evaluates against.

        `source` is deliberately absent. A policy that could read it would be
        able to behave differently in simulation and in live mode, and the
        entire mode-parity guarantee would be a claim rather than a property.
        """
        return {
            "actor.role": str(self.actor.role),
            "actor.team": self.actor.team,
            "actor.seniority": self.actor.seniority,
            "actor.prod_access": self.actor.prod_access,
            "actor.risk_score": self.actor.risk_score,
            "actor.spend_today_usd": self.actor.spend_today_usd,
            "actor.daily_budget_usd": self.actor.daily_budget_usd,
            "actor.sessions_today": self.actor.sessions_today,
            "actor.is_low_confidence": self.actor.is_low_confidence,
            "request.task_type": self.task_type,
            "request.complexity": self.complexity,
            "request.repo": self.repo,
            "request.environment": str(self.environment),
            "request.prompt_len": self.prompt_len,
            "request.requested_model": self.requested_model,
            "request.est_cost_usd": self.est_cost_usd,
            "request.est_input_tokens": self.est_input_tokens,
            "request.routed_model": self.routed_model,
            "request.findings_count": len(self.findings),
            "request.finding_types": [f.detector for f in self.findings],
            "request.off_hours": self.off_hours,
        }


class ActionContext(BaseModel):
    """Everything Gate 2 needs, and nothing about where it came from."""

    source: Source = Source.SIM
    actor: ActorContext
    task_id: str
    repo: str = ""
    environment: Environment = Environment.LOCAL
    elapsed_sim_s: int = 0
    tokens_so_far: int = 0
    cost_so_far_usd: float = 0.0
    actions_so_far: int = 0
    blocked_so_far: int = 0
    tool: ToolName = ToolName.READ_FILE
    args: dict[str, Any] = Field(default_factory=dict)
    args_digest: str = ""
    target_resource: str = ""
    resource_sensitivity: Sensitivity = Sensitivity.LOW
    is_repo_in_scope: bool = True
    is_secret_path: bool = False
    is_protected_branch: bool = False
    is_external_host: bool = False
    repeat_count_5m: int = 0
    iteration_index: int = 0
    sim_ts: int = 0

    def policy_view(self) -> dict[str, Any]:
        """The flat field map the DSL evaluates against. No `source`."""
        return {
            "actor.role": str(self.actor.role),
            "actor.team": self.actor.team,
            "actor.seniority": self.actor.seniority,
            "actor.prod_access": self.actor.prod_access,
            "actor.risk_score": self.actor.risk_score,
            "actor.is_low_confidence": self.actor.is_low_confidence,
            "action.tool": str(self.tool),
            "action.environment": str(self.environment),
            "action.target_resource": self.target_resource,
            "action.resource_sensitivity": str(self.resource_sensitivity),
            "action.repeat_count_5m": self.repeat_count_5m,
            "action.iteration_index": self.iteration_index,
            "task.repo": self.repo,
            "task.is_repo_in_scope": self.is_repo_in_scope,
            "task.is_secret_path": self.is_secret_path,
            "task.is_protected_branch": self.is_protected_branch,
            "task.is_external_host": self.is_external_host,
            "task.cost_so_far_usd": self.cost_so_far_usd,
            "task.blocked_so_far": self.blocked_so_far,
            "task.elapsed_sim_s": self.elapsed_sim_s,
        }

    @property
    def grant_key(self) -> str:
        return f"{self.tool}|{self.target_resource}|{self.environment}"


class DecisionResult(BaseModel):
    """What a gate returns. Always explainable: the matched policies are part
    of the answer, not a side effect.
    """

    decision: Decision = Decision.ALLOW
    reason_code: str = "clean"
    matched_policies: list[PolicyMatch] = Field(default_factory=list)
    message: str | None = None
    approval_id: str | None = None
    route_override: str | None = None
    redacted_text: str | None = None
    latency_ms: float = 0.0


# ──────────────────────────────────────────────────────────────────────
# Run + repositories
# ──────────────────────────────────────────────────────────────────────


class SimRun(BaseModel):
    id: str
    seed: int
    employee_count: int = 20
    speed: int = 1
    scenario: str = "demo"
    status: Literal["created", "running", "paused", "completed"] = "created"
    sim_ts: int = 0
    start_sim_ts: int = 0
    sim_day: int = 0
    created_at: str = ""
    last_seq: int = 0


class Repository(BaseModel):
    name: str
    team: str
    protected_branches: list[str] = Field(default_factory=list)
    has_secrets: bool = False
    environments: list[Environment] = Field(default_factory=list)


class OfficeAvatarState(BaseModel):
    """One avatar, as the office renders it.

    Derived entirely from telemetry. The canvas holds no authority -- if it
    and the Live Feed disagree, the feed is right and the scene resnapshots.
    """

    employee_id: str
    sprite_key: str
    tile: dict[str, int]
    facing: Literal["n", "e", "s", "w"] = "s"
    fsm: Literal["idle", "walking", "working", "waiting", "blocked", "meeting"] = "idle"
    badge: Literal["none", "working", "waiting", "blocked", "anomaly"] = "none"
    name: str = ""
    role: str = ""
    team: str = ""
    risk_score: int = 0
    status: TaskStatus = TaskStatus.QUEUED
    current_task_title: str | None = None


class OfficeSnapshot(BaseModel):
    """The rehydration payload.

    Served on mount, on a WebSocket gap over 500 events, and on exit from
    100x. `seq` is where the stream resumes.
    """

    run_id: str
    seq: int = 0
    sim_ts: int = 0
    speed: int = 1
    avatars: list[OfficeAvatarState] = Field(default_factory=list)
    pending_approvals: int = 0


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def digest_args(tool: ToolName | str, args: dict[str, Any]) -> str:
    """SHA-256 of normalised tool arguments.

    Identical repeated attempts are countable because of this, and a repeat
    count is one of the strongest adversarial signals available -- an agent
    that keeps trying variations of a blocked path is telling you something.
    """
    normalised = json.dumps(
        {"tool": str(tool), "args": args}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(normalised.encode()).hexdigest()
