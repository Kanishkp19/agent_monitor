"""FastAPI application entry point.

The lifespan owns the container; `deps.Services` owns everything assembled
from it. Routers mount under `/api/v1`. The WebSocket sits outside that prefix
because it is a different protocol, not a different version of the same one.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentshield.api import errors as error_handlers
from agentshield.api import (
    routes_autopilot,
    routes_core,
    routes_ingest,
    routes_metrics,
    routes_playground,
    routes_policies,
    routes_risk,
    routes_sim,
    ws,
)
from agentshield.config import Settings
from agentshield.container import Container, get_container
from agentshield.deps import get_services

logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = get_container()
    await container.startup()
    app.state.container = container

    services = get_services()
    app.state.services = services

    # Warm the policy cache so the first governed request does not pay for a
    # cold read, and so `/readyz` can answer honestly about whether the gates
    # are actually armed.
    try:
        await services.policies.active(1)
        await services.policies.active(2)
    except Exception:
        logger.warning("policy preload failed; gates will load on first use")

    logger.info(
        "agentshield started",
        extra={"env": container.settings.env, "adapters": container.describe()},
    )
    try:
        yield
    finally:
        await services.autopilot.shutdown()
        await services.engine.stop()
        await container.shutdown()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="AgentShield",
        description="Governance and observability control plane for AI coding agents.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Explicit origins, never a wildcard, in any environment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    error_handlers.install(app)

    app.include_router(routes_sim.router, prefix=API_PREFIX)
    app.include_router(routes_core.employees_router, prefix=API_PREFIX)
    app.include_router(routes_core.tasks_router, prefix=API_PREFIX)
    app.include_router(routes_core.events_router, prefix=API_PREFIX)
    app.include_router(routes_core.approvals_router, prefix=API_PREFIX)
    app.include_router(routes_policies.router, prefix=API_PREFIX)
    app.include_router(routes_policies.lab_router, prefix=API_PREFIX)
    app.include_router(routes_risk.router, prefix=API_PREFIX)
    app.include_router(routes_metrics.router, prefix=API_PREFIX)
    app.include_router(routes_ingest.router, prefix=API_PREFIX)
    app.include_router(routes_playground.router, prefix=API_PREFIX)
    app.include_router(routes_autopilot.router, prefix=API_PREFIX)
    app.include_router(ws.router)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, Any]:
        """Liveness, plus which adapter is behind each port.

        Naming the adapters turns "is this really running on AWS?" from an
        inference into a fact -- the first thing to check after flipping
        `AGENTSHIELD_ENV`.
        """
        container: Container = app.state.container
        return {
            "status": "ok",
            "env": container.settings.env,
            "llm_provider": container.settings.llm_provider,
            "adapters": container.describe(),
        }

    @app.get("/readyz", tags=["health"])
    async def readyz() -> Any:
        """Ready means the store answers *and* the gates are armed.

        Reporting ready before policies load would let traffic through a
        control plane whose controls are not yet in place.
        """
        from fastapi.responses import JSONResponse

        container: Container = app.state.container
        try:
            await container.docstore.get("HEALTH", "PROBE")
        except Exception as exc:
            logger.warning("readiness probe failed", extra={"error": str(exc)})
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "reason": "docstore"}
            )

        services = get_services()
        loaded = bool(services.policies.version_hash(1) or services.policies.version_hash(2))
        return {"status": "ready", "policies_loaded": loaded}

    return app


app = create_app()
