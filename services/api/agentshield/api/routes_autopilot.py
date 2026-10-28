"""Token-protected API for curated coding fixtures and immutable job evidence."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from agentshield.api.schemas import ok
from agentshield.autopilot.schemas import AutopilotJobSpec
from agentshield.autopilot.workspace import UnknownFixture
from agentshield.deps import Services, get_services

router = APIRouter(prefix="/autopilot", tags=["autopilot"])

MISSING_KEY = (
    "NEBIUS_API_KEY is not configured. Set NEBIUS_API_KEY in services/api/.env or export it."
)


def _authorized(
    authorization: str = Header(default=""), services: Services = Depends(get_services)
) -> Services:
    token = services.container.settings.autopilot_demo_token
    supplied = authorization.removeprefix("Bearer ")
    if not token:
        raise HTTPException(503, "AUTOPILOT_DEMO_TOKEN must be configured")
    if not hmac.compare_digest(supplied, token):
        raise HTTPException(401, "Autopilot token required")
    return services


def _configured(services: Services = Depends(_authorized)) -> Services:
    if not services.container.settings.nebius_api_key.strip():
        raise HTTPException(422, MISSING_KEY)
    return services


@router.get("/configuration", responses={422: {"description": MISSING_KEY}})
async def configuration(services: Services = Depends(_configured)) -> dict[str, Any]:
    return ok({"configured": True, "model": services.container.settings.nebius_model})


@router.get("/fixtures")
async def fixtures(services: Services = Depends(_authorized)) -> dict[str, Any]:
    return ok(
        [manifest.model_dump() for manifest in services.autopilot.manager.available_fixtures()]
    )


@router.post("/jobs", status_code=202)
async def create_job(
    spec: AutopilotJobSpec, services: Services = Depends(_configured)
) -> dict[str, Any]:
    try:
        return ok(await services.autopilot.create(spec))
    except UnknownFixture as exc:
        raise HTTPException(400, str(exc)) from exc


async def _job(job_id: str, services: Services) -> dict[str, Any]:
    job = await services.autopilot.get(job_id)
    if job is None:
        raise HTTPException(404, "Autopilot job not found")
    return job


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, services: Services = Depends(_configured)) -> dict[str, Any]:
    return ok(await _job(job_id, services))


@router.get("/jobs/{job_id}/events")
async def get_events(
    job_id: str, since_seq: int = Query(0, ge=0), services: Services = Depends(_authorized)
) -> dict[str, Any]:
    await _job(job_id, services)
    events = await services.autopilot.events(job_id, since_seq)
    return ok({"events": events, "next_seq": events[-1]["detail"]["seq"] if events else since_seq})


@router.get("/jobs/{job_id}/report")
async def report(job_id: str, services: Services = Depends(_authorized)) -> dict[str, Any]:
    job = await _job(job_id, services)
    if job["state"] not in ("completed", "failed", "blocked"):
        raise HTTPException(409, "Job is still running")
    events = await services.autopilot.events(job_id)
    return ok({**job, "events": events})


@router.post("/jobs/{job_id}/reset", status_code=202)
async def reset_job(job_id: str, services: Services = Depends(_configured)) -> dict[str, Any]:
    job = await services.autopilot.reset(job_id)
    if job is None:
        raise HTTPException(409, "Job must exist and be terminal before reset")
    return ok(job)
