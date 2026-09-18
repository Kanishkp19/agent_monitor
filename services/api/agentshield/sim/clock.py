"""The simulated clock -- the only implementation of `ClockPort`.

One implementation in both environments, deliberately (decision D9). Simulated
time is domain logic, not infrastructure. A second, wall-clock implementation
would create a path where the same seed produces different output, and without
determinism the detector's precision and recall are decoration.

Everything that expires, sweeps or schedules reads `sim_ts`. Nothing reads wall
time except log timestamps and the `time` field on the event envelope.
"""

from __future__ import annotations

from datetime import UTC, datetime

from agentshield.domain.enums import SimSpeed


class SimClock:
    """Monotonic simulated time, advanced explicitly by the tick loop.

    `sim_ts` never moves on its own. Nothing in the system may infer elapsed
    simulated time from elapsed wall time -- that would make a fast-forward and
    a real-time run produce different event streams from the same seed.
    """

    def __init__(self, seed_ts: int, speed: SimSpeed = SimSpeed.REALTIME) -> None:
        self._sim_ts = int(seed_ts)
        self._speed = SimSpeed(speed)

    @property
    def sim_ts(self) -> int:
        return self._sim_ts

    @property
    def speed(self) -> SimSpeed:
        return self._speed

    def now_wall(self) -> datetime:
        """Real time. For log lines and the envelope's `time` field only."""
        return datetime.now(UTC)

    def advance(self, sim_seconds: int) -> int:
        if sim_seconds < 0:
            raise ValueError("simulated time does not run backwards")
        self._sim_ts += sim_seconds
        return self._sim_ts

    def set_speed(self, speed: SimSpeed) -> None:
        self._speed = SimSpeed(speed)

    # ── derived views, used by the diurnal task sampler and the UI ────

    @property
    def sim_datetime(self) -> datetime:
        return datetime.fromtimestamp(self._sim_ts, tz=UTC)

    @property
    def sim_hour(self) -> int:
        """Hour of the simulated day, 0-23. Drives the working-hours curve."""
        return self.sim_datetime.hour

    @property
    def sim_date(self) -> str:
        """`YYYY-MM-DD` in simulated time -- the counter partition key."""
        return self.sim_datetime.strftime("%Y-%m-%d")

    def __repr__(self) -> str:
        return f"SimClock(sim_ts={self._sim_ts}, speed={self._speed.name})"
