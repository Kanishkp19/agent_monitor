"""Every enum in AgentShield.

Mirrored to TypeScript by `packages/contracts/generate.py`. Do not hand-write
the TS side.

`StrEnum` requires Python 3.11+.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class Decision(StrEnum):
    """The four outcomes either gate can return.

    Precedence is fixed and never configurable: block > review > redact > allow.
    """

    ALLOW = "allow"
    REDACT = "redact"
    REVIEW = "review"
    BLOCK = "block"


class Gate(IntEnum):
    REQUEST = 1
    ACTION = 2


class Role(StrEnum):
    INTERN = "engineering_intern"
    ENGINEER = "engineer"
    SENIOR_ENGINEER = "senior_engineer"
    MANAGER = "manager"
    SENIOR_MANAGER = "senior_manager"
    DEVOPS = "devops"
    CEO = "ceo"


class Archetype(StrEnum):
    """Six behavioural templates. See `docs/DECISIONS-RESOLVED.md` C2 --
    `senior_manager` and `ceo` are roles, not archetypes; they map onto
    `MANAGER` and `EXEC` respectively.
    """

    INTERN = "intern"
    ENGINEER = "engineer"
    SENIOR = "senior_engineer"
    MANAGER = "manager"
    DEVOPS = "devops"
    EXEC = "exec"


class ScenarioProfile(StrEnum):
    """Simulation-internal. NEVER exposed via the API.

    Read by `sim/`, written to a ground-truth key the risk engine has no query
    path to, and consumed only by `infra/scripts/evaluate.py` after the fact.
    If you find yourself importing this into `risk/`, stop.
    """

    NORMAL = "normal"
    SLOPPY = "sloppy"
    ADVERSARIAL = "adversarial"


class Environment(StrEnum):
    """The deploy target of a governed action -- not the deploy target of
    AgentShield itself (that is `config.DeploymentEnv`).
    """

    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class ToolName(StrEnum):
    READ_FILE = "read_file"
    EDIT_FILE = "edit_file"
    RUN_TESTS = "run_tests"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    CALL_API = "call_api"
    DEPLOY = "deploy"
    EXTERNAL_FETCH = "external_fetch"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    REQUESTING = "requesting"
    AWAITING_APPROVAL = "awaiting_approval"
    WORKING = "working"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    DENIED = "denied"
    DENIED_TIMEOUT = "denied_timeout"
    FAILED = "failed"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED_ONCE = "approved_once"
    APPROVED_SESSION = "approved_session"
    DENIED = "denied"
    EXPIRED = "expired"


class Sensitivity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SimSpeed(IntEnum):
    PAUSED = 0
    REALTIME = 1
    FAST = 10
    TURBO = 100


class Source(StrEnum):
    """Telemetry metadata only.

    Deliberately absent from the policy field allowlist -- a policy that could
    read this could behave differently in simulation and in live mode, which
    would make the whole mode-parity guarantee a lie. See `DESIGN.md` section 4.
    """

    SIM = "sim"
    LIVE = "live"


# Terminal states, named once so state machines and UI filters agree.
TERMINAL_TASK_STATUSES: frozenset[TaskStatus] = frozenset(
    {
        TaskStatus.COMPLETED,
        TaskStatus.BLOCKED,
        TaskStatus.DENIED,
        TaskStatus.DENIED_TIMEOUT,
        TaskStatus.FAILED,
    }
)

TERMINAL_APPROVAL_STATUSES: frozenset[ApprovalStatus] = frozenset(
    {
        ApprovalStatus.APPROVED_ONCE,
        ApprovalStatus.APPROVED_SESSION,
        ApprovalStatus.DENIED,
        ApprovalStatus.EXPIRED,
    }
)
