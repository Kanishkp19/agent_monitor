"""The global error handler and the wire envelope.

Every non-2xx response from `/api/v1/*` has the same shape, from
`docs/02-TRD.md` section 6.1:

    {"error": {"code": "...", "message": "...", "field": "...", "details": {}}}

Never a bare FastAPI 422 for a business rule. A 422 with Pydantic's default
body tells a client that *something* about their JSON was wrong; the envelope
tells them which field and what would be acceptable, which is the difference
between a fixable error and a support ticket.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agentshield.domain.errors import AgentShieldError

logger = logging.getLogger(__name__)


def install(app: FastAPI) -> None:
    @app.exception_handler(AgentShieldError)
    async def _domain_error(request: Request, exc: AgentShieldError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.envelope())

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Translate Pydantic's report into our envelope.

        `field` is the JSON path an editor can highlight, which is the whole
        reason for doing this rather than letting FastAPI answer.
        """
        first = exc.errors()[0] if exc.errors() else {}
        location = [str(part) for part in first.get("loc", []) if part != "body"]
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "validation_failed",
                    "message": first.get("msg", "The request body was not valid."),
                    "field": ".".join(location) or None,
                    "details": {"errors": _safe_errors(exc)},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Anything unexpected.

        The correlation id goes to the client and to the log; the exception
        text goes only to the log. Leaking a stack trace to a browser is how
        internal paths and library versions end up in a bug report.
        """
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(
            "unhandled error",
            extra={"correlation_id": correlation_id, "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side.",
                    "details": {"correlation_id": correlation_id},
                }
            },
        )


def _safe_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    """Pydantic error objects can carry the offending input.

    That input may be a prompt containing a secret, so only the location and
    the message cross the boundary.
    """
    return [
        {
            "field": ".".join(str(p) for p in e.get("loc", []) if p != "body"),
            "message": str(e.get("msg", "")),
        }
        for e in exc.errors()[:10]
    ]
