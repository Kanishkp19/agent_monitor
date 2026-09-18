"""ClockPort -- simulated time.

The only port with **one** implementation in both environments, deliberately
(decision D9). Simulated time is domain logic, not infrastructure. Giving it a
second, wall-clock implementation would invite a code path where the same seed
produces different output, which would destroy determinism and with it every
number the detector reports.

Everything that expires, sweeps or schedules reads `sim_ts`. Nothing reads
wall time except log timestamps.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from agentshield.domain.enums import SimSpeed


@runtime_checkable
class ClockPort(Protocol):
    @property
    def sim_ts(self) -> int:
        """Current simulated unix time, in seconds."""
        ...

    @property
    def speed(self) -> SimSpeed: ...

    def now_wall(self) -> datetime: ...

    def advance(self, sim_seconds: int) -> int:
        """Move simulated time forward. Returns the new `sim_ts`."""
        ...

    def set_speed(self, speed: SimSpeed) -> None: ...
