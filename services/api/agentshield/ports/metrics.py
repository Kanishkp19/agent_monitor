"""MetricsPort -- counters, gauges and timings.

The local adapter emits the same CloudWatch EMF JSON blob to stdout that the
AWS adapter sends to CloudWatch, so a dashboard built against one works against
the other.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsPort(Protocol):
    def count(self, name: str, value: float = 1, **dims: str) -> None: ...

    def gauge(self, name: str, value: float, **dims: str) -> None: ...

    def timing(self, name: str, ms: float, **dims: str) -> None: ...
