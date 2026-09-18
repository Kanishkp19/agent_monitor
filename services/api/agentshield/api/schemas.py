"""Request and response models for the REST API.

Validation lives here so a route body is rejected before it reaches any
domain code. `docs/05-BACKEND-SCHEMA.md` section 7.1.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from agentshield.domain.enums import ToolName
from agentshield.domain.errors import PolicyInvalid
from agentshield.domain.models import ApproverSpec
from agentshield.governance import dsl


class CreateRunRequest(BaseModel):
    seed: int | None = Field(None, ge=0, le=2**31 - 1)
    employee_count: int = Field(20, ge=5, le=50)
    speed: Literal[0, 1, 10, 100] = 1
    scenario: str = Field("demo", pattern=r"^[a-z0-9_-]{1,32}$")
    start_sim_ts: int | None = None
    seed_history: bool = False
    """Pre-run 14 simulated days so risk baselines exist.

    Without it every employee is `low_confidence` and the risk engine has
    nothing to compare against -- the documented cause of "all scores are
    50-ish".
    """


class ControlRequest(BaseModel):
    action: Literal["start", "pause", "resume", "reset", "set_speed"]
    speed: Literal[0, 1, 10, 100] | None = None

    @model_validator(mode="after")
    def speed_required(self) -> ControlRequest:
        if self.action == "set_speed" and self.speed is None:
            raise ValueError("speed is required when action is set_speed")
        return self


class AdvanceRequest(BaseModel):
    sim_days: int | None = Field(None, ge=1, le=30)
    sim_hours: int | None = Field(None, ge=1, le=720)

    @model_validator(mode="after")
    def exactly_one(self) -> AdvanceRequest:
        if (self.sim_days is None) == (self.sim_hours is None):
            raise ValueError("provide exactly one of sim_days or sim_hours")
        return self


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approve_once", "approve_session", "deny"]
    approver_id: str = Field(pattern=r"^emp_\d{3}$")
    note: str | None = Field(None, max_length=500)


class PolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=80)
    gate: Literal[1, 2]
    priority: int = Field(50, ge=0, le=999)
    effect: Literal["allow", "redact", "review", "block"]
    enabled: bool = True
    is_draft: bool = False
    when: dict[str, Any]
    approver: ApproverSpec | None = None
    ttl_sim_seconds: int = Field(300, ge=30, le=86_400)
    route_override: str | None = None
    message: str = Field(min_length=5, max_length=200)

    @model_validator(mode="after")
    def validate_policy(self) -> PolicyCreate:
        errors = dsl.validate(self.when, self.gate)
        if errors:
            path, message = errors[0]
            raise PolicyInvalid(message, field=path, details={"errors": errors})

        if self.effect == "review" and self.approver is None:
            raise ValueError("approver is required when effect is review")

        # There is no partial read of a secret file. A redact at Gate 2 would
        # be a decision the runtime cannot honour.
        if self.effect == "redact" and self.gate == 2:
            raise ValueError("redact is not a valid effect at gate 2")

        return self


class PolicyPatch(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=80)
    priority: int | None = Field(None, ge=0, le=999)
    effect: Literal["allow", "redact", "review", "block"] | None = None
    enabled: bool | None = None
    is_draft: bool | None = None
    when: dict[str, Any] | None = None
    approver: ApproverSpec | None = None
    ttl_sim_seconds: int | None = Field(None, ge=30, le=86_400)
    route_override: str | None = None
    message: str | None = Field(None, min_length=5, max_length=200)


class PolicyToggle(BaseModel):
    enabled: bool


class PolicyValidateRequest(BaseModel):
    when: dict[str, Any]
    gate: Literal[1, 2]


class PolicyLabRequest(BaseModel):
    run_id: str
    draft_policy: PolicyCreate
    window_sim_hours: int = Field(24, ge=1, le=168)


class PolicyLabPromoteRequest(BaseModel):
    policy_lab_id: str


# ──────────────────────────────────────────────────────────────────────
# Live Mode ingest
# ──────────────────────────────────────────────────────────────────────


class IngestGate1Request(BaseModel):
    """A real agent asking permission before a model call.

    Note what is *not* here: any assertion of who the caller is. The actor --
    and therefore the role every policy evaluates against -- is resolved
    server-side from the bearer token. An agent cannot assert its own role.
    """

    task_ref: str = Field(max_length=128)
    task_type: str
    complexity: Literal["trivial", "standard", "complex"]
    repo: str = Field(pattern=r"^[a-z0-9._-]{1,64}$")
    environment: Literal["local", "staging", "production"]
    prompt: str = Field(max_length=100_000)
    requested_model: str | None = None


class IngestGate2Request(BaseModel):
    task_id: str
    tool: ToolName
    args: dict[str, Any]
    iteration: int = Field(ge=0, le=64)


class IngestEventRequest(BaseModel):
    task_id: str
    detail_type: str
    payload: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────
# Responses
# ──────────────────────────────────────────────────────────────────────


class Envelope(BaseModel):
    """Every 2xx body is `{"data": ...}`.

    A consistent wrapper means a client's error check is one branch rather
    than a shape sniff per endpoint.
    """

    data: Any


def ok(data: Any) -> dict[str, Any]:
    return {"data": data}
