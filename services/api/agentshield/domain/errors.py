"""Domain errors, each mapping to one entry in the API error envelope.

`docs/02-TRD.md` section 6.1 fixes the wire shape. Raising these rather than
`HTTPException` keeps the governance core free of any web framework, which is
what lets the simulator and the ingest API share one code path.
"""

from __future__ import annotations

from typing import Any


class AgentShieldError(Exception):
    """Base for everything the API converts into an error envelope."""

    code: str = "internal_error"
    status: int = 500

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.details = details or {}

    def envelope(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.field:
            error["field"] = self.field
        if self.details:
            error["details"] = self.details
        return {"error": error}


class ValidationFailed(AgentShieldError):
    code = "validation_failed"
    status = 400


class PolicyInvalid(AgentShieldError):
    """DSL validation failure. Always carries the offending JSON path.

    An unknown field is a validation error with a path, never a silent
    no-match -- a policy that quietly never fires is worse than one that
    refuses to save.
    """

    code = "policy_invalid"
    status = 400


class RunNotFound(AgentShieldError):
    code = "run_not_found"
    status = 404


class NotFound(AgentShieldError):
    code = "not_found"
    status = 404


class ApprovalAlreadyDecided(AgentShieldError):
    code = "approval_already_decided"
    status = 409


class RunBusy(AgentShieldError):
    code = "run_busy"
    status = 409


class Unauthorized(AgentShieldError):
    code = "unauthorized"
    status = 401


class RateLimited(AgentShieldError):
    code = "rate_limited"
    status = 429


class IllegalTransition(AgentShieldError):
    """A state machine was asked for a move it does not have.

    Never silently corrected. An illegal transition is a bug in the caller,
    and swallowing it produces a task whose history cannot be trusted.
    """

    code = "validation_failed"
    status = 400
