"""Dependency wiring.

Everything the routes need, assembled once from the container. There are no
module-level singletons anywhere else in the backend -- a route that reached
for a global would be a route that could not be tested against a temporary
store.

This module also owns the one `SimulationEngine` instance and the WebSocket
hub, because both are process-wide and both need the same emitter.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from agentshield.agent.runner import AgentRunner, RunnerDeps
from agentshield.autopilot.runner import AutopilotCoordinator
from agentshield.autopilot.workspace import WorkspaceManager
from agentshield.container import Container, get_container
from agentshield.domain.enums import Source
from agentshield.governance.approvals import ApprovalEngine
from agentshield.governance.budget import BudgetGuard
from agentshield.governance.gate1 import Gate1
from agentshield.governance.gate2 import Gate2
from agentshield.governance.policy_engine import PolicyEngine
from agentshield.risk.baseline import BaselineStore
from agentshield.risk.engine import RiskEngine
from agentshield.risk.incidents import IncidentManager
from agentshield.risk.isolation import AnomalyDetector
from agentshield.risk.scoped_store import RiskScopedDocStore
from agentshield.sandbox.executor import Sandbox
from agentshield.sandbox.vfs import VirtualFileSystem
from agentshield.sim.engine import EngineDeps, SimulationEngine
from agentshield.sim.scenarios import ScenarioEngine
from agentshield.sim.seed import Seeder
from agentshield.sim.snapshot import SnapshotBuilder
from agentshield.sim.task_generator import TaskGenerator
from agentshield.telemetry.counters import Counters
from agentshield.telemetry.emitter import TelemetryEmitter


class Services:
    """The assembled object graph.

    Built once per process. `risk/` receives a `RiskScopedDocStore` rather
    than the raw store -- the wrapper is applied here, at the only place that
    could forget to, which is why it is one line and not a convention.
    """

    def __init__(self, container: Container) -> None:
        self.container = container
        settings = container.settings

        self.policies = PolicyEngine(container.docstore)
        self.counters = Counters(container.docstore)
        self.hub = WebSocketHub()

        # The detector's view of the world. Constructed before the emitter so
        # it can be handed in as the observer -- and constructed *here*, at
        # the only place that could forget to wrap it, which is why the
        # wrapper is one line rather than a convention.
        self.risk_store = RiskScopedDocStore(container.docstore)
        self.baselines = BaselineStore(
            self.risk_store, min_sessions=settings.risk_min_sessions_for_baseline
        )
        self.detector = AnomalyDetector(
            n_estimators=settings.isolation_forest_estimators,
            contamination=settings.isolation_forest_contamination,
            seed=settings.sim_seed,
        )
        self.incidents = IncidentManager(
            container.docstore, threshold=settings.risk_incident_threshold
        )
        self.risk = RiskEngine(
            store=self.risk_store,
            baselines=self.baselines,
            detector=self.detector,
            incidents=self.incidents,
            min_sessions=settings.risk_min_sessions_for_baseline,
        )

        self.emitter = TelemetryEmitter(
            docstore=container.docstore,
            bus=container.bus,
            metrics=container.metrics,
            clock=container.clock,
            source=Source.SIM,
            risk=self.risk,
            broadcaster=self.hub.broadcast,
        )

        self.budget = BudgetGuard(self.counters)
        self.gate1 = Gate1(
            policies=self.policies,
            budget=self.budget,
            redaction_enabled=settings.redaction_enabled,
        )
        self.gate2 = Gate2(policies=self.policies)

        self.autopilot = AutopilotCoordinator(
            manager=WorkspaceManager(
                fixtures_dir=settings.autopilot_fixtures_path,
                workspaces_dir=settings.autopilot_workspaces_path,
            ),
            llm=container.autopilot_llm,
            gate1=self.gate1,
            gate2=self.gate2,
            store=container.docstore,
            emitter=TelemetryEmitter(
                docstore=container.docstore,
                bus=container.bus,
                metrics=container.metrics,
                clock=container.clock,
                source=Source.LIVE,
                broadcaster=self.hub.broadcast,
            ),
        )

        self.approvals = ApprovalEngine(
            docstore=container.docstore,
            clock=container.clock,
            emitter=self.emitter,
            default_ttl=settings.approval_ttl_sim_seconds,
        )

        self.vfs = VirtualFileSystem(container.docstore)
        self.sandbox = Sandbox(self.vfs)
        self.seeder = Seeder(container.docstore, self.policies)
        self.snapshots = SnapshotBuilder(container.docstore)

        self.runner = AgentRunner(
            RunnerDeps(
                llm=container.llm,
                gate2=self.gate2,
                sandbox=self.sandbox,
                approvals=self.approvals,
                emitter=self.emitter,
                docstore=container.docstore,
                clock=container.clock,
                max_iterations=settings.llm_max_iterations,
                retry_threshold=settings.retry_loop_threshold,
            )
        )

        self.generator = TaskGenerator(
            seed=settings.sim_seed,
            llm_invocation_rate=settings.sim_llm_invocation_rate,
        )
        self.scenarios = ScenarioEngine(
            seed=settings.sim_seed, scenario_file=settings.scenario_path
        )

        self.engine = SimulationEngine(
            EngineDeps(
                docstore=container.docstore,
                blobs=container.blobs,
                clock=container.clock,
                emitter=self.emitter,
                counters=self.counters,
                gate1=self.gate1,
                runner=self.runner,
                seeder=self.seeder,
                generator=self.generator,
                scenarios=self.scenarios,
                max_concurrent=settings.sim_max_concurrent_sessions,
                llm_provider=settings.llm_provider,
                deterministic_llm_factory=container.deterministic_llm,
            )
        )
        self.engine.on_downshift(self.hub.notify_downshift)


class WebSocketHub:
    """Fan-out to connected browsers.

    Coalescing is speed-aware: at 1x every event is a frame; at 10x the
    server batches into 250 ms groups, because a browser cannot usefully
    render two hundred frames a second and trying is what floods the tab.
    """

    def __init__(self) -> None:
        self._connections: list[Any] = []
        self._pending: list[dict[str, Any]] = []

    def add(self, websocket: Any) -> None:
        self._connections.append(websocket)

    def remove(self, websocket: Any) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, envelope: Any) -> None:
        frame = {
            "kind": "event",
            "seq": envelope.detail.seq,
            "events": [envelope.model_dump(mode="json")],
        }
        await self.send(frame)

    async def send(self, frame: dict[str, Any]) -> None:
        dead: list[Any] = []
        for connection in list(self._connections):
            try:
                await connection.send_json(frame)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.remove(connection)

    def notify_downshift(self, run_id: str, speed: Any) -> None:
        """Queued rather than sent: this is called from the tick loop, which
        is not a place to await a socket write.
        """
        self._pending.append(
            {"kind": "progress", "seq": 0, "progress": {"speed_downshift": int(speed)}}
        )

    def drain_pending(self) -> list[dict[str, Any]]:
        pending, self._pending = self._pending, []
        return pending


@lru_cache
def get_services() -> Services:
    return Services(get_container())


def reset_services() -> None:
    """Drop the cached graph. Tests use this between cases."""
    get_services.cache_clear()
