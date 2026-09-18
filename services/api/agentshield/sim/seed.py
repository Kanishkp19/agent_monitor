"""Seeding a run: employees, repositories, policies, desks.

`make seed` and `POST /sim/runs` both land here. Everything it writes is
derived from the run seed, so two runs with the same seed produce the same
company down to each employee's daily budget.

Desk assignment happens *here*, not in the renderer. The office reads
`desk` and `desk_slot` off the employee record; if the renderer decided where
people sat, a page reload would move everyone and rehydration would be a lie.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import ulid

from agentshield.domain.enums import Gate, ScenarioProfile
from agentshield.domain.models import Employee, Policy, Repository, SimRun
from agentshield.governance.policy_engine import PolicyEngine
from agentshield.ports.docstore import DocItem, DocStorePort
from agentshield.sandbox.vfs import VirtualFileSystem
from agentshield.sim.office_map import desk_for_slot
from agentshield.sim.persona import build_persona, seeded_rng
from agentshield.sim.seed_data import EMPLOYEES, POLICIES, REPOS, SHOWCASE_DRAFT

logger = logging.getLogger(__name__)

# Eight base sprites cover twenty employees; variety comes from a deterministic
# tint drawn from the employee id.
SPRITE_COUNT = 8


class Seeder:
    def __init__(self, docstore: DocStorePort, policies: PolicyEngine) -> None:
        self._docstore = docstore
        self._policies = policies
        self._vfs = VirtualFileSystem(docstore)

    async def create_run(
        self,
        *,
        seed: int,
        employee_count: int = 20,
        speed: int = 1,
        scenario: str = "demo",
        start_sim_ts: int = 1758182400,
    ) -> tuple[SimRun, list[Employee]]:
        run = SimRun(
            id=f"run_{ulid.new().str[-8:].lower()}",
            seed=seed,
            employee_count=employee_count,
            speed=speed,
            scenario=scenario,
            sim_ts=start_sim_ts,
            start_sim_ts=start_sim_ts,
            created_at=datetime.now(UTC).isoformat(),
        )

        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run.id}",
                sk="META",
                gsi1pk="RUNS",
                gsi1sk=run.created_at,
                body=run.model_dump(mode="json"),
            )
        )

        employees = await self.seed_employees(run.id, seed, employee_count)
        await self.seed_repositories()
        await self._vfs.seed()
        await self.seed_policies()

        logger.info(
            "run seeded",
            extra={"run_id": run.id, "employees": len(employees), "seed": seed},
        )
        return run, employees

    # ── employees ────────────────────────────────────────────────────

    async def seed_employees(self, run_id: str, seed: int, count: int = 20) -> list[Employee]:
        """The roster from `docs/05-BACKEND-SCHEMA.md` section 10.2.

        `count` under 20 truncates the roster; over 20 is capped, because the
        named twenty are what the scenario scripts and the office floor plan
        assume. A run with 50 employees would need 50 desks.
        """
        roster = EMPLOYEES[: min(count, len(EMPLOYEES))]
        employees: list[Employee] = []
        items: list[DocItem] = []

        for record in roster:
            persona = build_persona(
                seed=seed,
                employee_id=record["id"],
                archetype=record["archetype"],
                role=record["role"],
                team=record["team"],
            )
            tile = desk_for_slot(record["room"], record["slot"])
            sprite_index = seeded_rng(seed, "sprite", record["id"]).randrange(SPRITE_COUNT)

            employee = Employee(
                id=record["id"],
                run_id=run_id,
                name=record["name"],
                role=record["role"],
                team=record["team"],
                agent_brand=record["agent"],
                persona=persona,
                sprite_key=f"char_{sprite_index:02d}",
                desk=tile,
                desk_slot=f"{record['room']}/{record['slot']}",
                manager_id=record["manager"],
                scenario_profile=record["profile"],
                # The adversary's clock starts when the run does. A non-zero
                # offset would let a demo begin mid-ladder.
                scenario_day_offset=0,
            )
            employees.append(employee)

            items.append(
                DocItem(
                    pk=f"RUN#{run_id}",
                    sk=f"EMP#{employee.id}",
                    gsi1pk=f"RUN#{run_id}#TEAM#{employee.team}",
                    gsi1sk=f"EMP#{employee.id}",
                    body=employee.model_dump(mode="json"),
                )
            )

        for start in range(0, len(items), 25):
            await self._docstore.batch_put(items[start : start + 25])

        return employees

    # ── repositories ─────────────────────────────────────────────────

    async def seed_repositories(self) -> list[Repository]:
        repos = [Repository.model_validate(r) for r in REPOS]
        await self._docstore.batch_put(
            [DocItem(pk=f"REPO#{r.name}", sk="META", body=r.model_dump(mode="json")) for r in repos]
        )
        return repos

    # ── policies ─────────────────────────────────────────────────────

    async def seed_policies(self, *, include_draft: bool = True) -> list[Policy]:
        """The twelve, plus the Policy Lab's showcase draft.

        Idempotent: reseeding rewrites version 1 rather than accumulating
        versions, so `make seed` twice does not produce a v2 of everything.
        """
        created: list[Policy] = []
        now = datetime.now(UTC).isoformat()

        specs: list[dict[str, Any]] = [dict(p) for p in POLICIES]
        if include_draft:
            specs.append(dict(SHOWCASE_DRAFT))

        for spec in specs:
            policy = Policy(
                id=spec["id"],
                version=1,
                name=spec["name"],
                gate=Gate(spec["gate"]),
                priority=int(spec.get("priority", 50)),
                effect=spec["effect"],
                enabled=bool(spec.get("enabled", True)),
                is_draft=bool(spec.get("is_draft", False)),
                when=spec["when"],
                approver=spec.get("approver"),
                ttl_sim_seconds=int(spec.get("ttl_sim_seconds", 300)),
                route_override=spec.get("route_override"),
                message=spec["message"],
                created_at=now,
                created_by="seed",
            )
            created.append(await self._policies.save(policy))

        self._policies.invalidate()
        return created

    # ── reads ────────────────────────────────────────────────────────

    async def load_employees(self, run_id: str) -> list[Employee]:
        """A3 -- every employee in a run."""
        page = await self._docstore.query(pk=f"RUN#{run_id}", sk_prefix="EMP#", limit=100)
        return [Employee.model_validate(item.body) for item in page.items]

    async def load_employee(self, run_id: str, employee_id: str) -> Employee | None:
        """A4."""
        item = await self._docstore.get(f"RUN#{run_id}", f"EMP#{employee_id}")
        return Employee.model_validate(item.body) if item else None

    async def load_run(self, run_id: str) -> SimRun | None:
        """A1."""
        item = await self._docstore.get(f"RUN#{run_id}", "META")
        return SimRun.model_validate(item.body) if item else None

    async def recent_runs(self, limit: int = 20) -> list[SimRun]:
        """A2."""
        page = await self._docstore.query(pk="RUNS", index="gsi1", ascending=False, limit=limit)
        return [SimRun.model_validate(item.body) for item in page.items]

    async def save_run(self, run: SimRun) -> None:
        await self._docstore.put(
            DocItem(
                pk=f"RUN#{run.id}",
                sk="META",
                gsi1pk="RUNS",
                gsi1sk=run.created_at,
                body=run.model_dump(mode="json"),
            )
        )


def adversarial_ids() -> list[str]:
    """Used only by `infra/scripts/evaluate.py`. Never by `risk/`."""
    return [e["id"] for e in EMPLOYEES if e["profile"] is ScenarioProfile.ADVERSARIAL]


def decoy_ids() -> list[str]:
    return [e["id"] for e in EMPLOYEES if e["profile"] is ScenarioProfile.SLOPPY]
