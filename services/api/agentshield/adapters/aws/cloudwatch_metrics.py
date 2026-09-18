"""CloudWatch implementation of MetricsPort, via Embedded Metric Format.

EMF means writing a structured log line and letting CloudWatch extract the
metric, rather than calling `PutMetricData` on every event. At the event rates
this system produces that difference is the difference between free and
expensive, and it removes an API call from the emitter's hot path.

The blob is byte-identical to the one `StdoutMetrics` prints locally, so a
dashboard built against either works against both.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Literal

Unit = Literal["Count", "Milliseconds", "None"]

# A dedicated logger so EMF blobs are never interleaved with prose logs --
# CloudWatch parses the whole line or nothing.
_emf = logging.getLogger("agentshield.emf")


class CloudWatchEmfMetrics:
    def __init__(self, namespace: str = "AgentShield") -> None:
        self._namespace = namespace

    def count(self, name: str, value: float = 1, **dims: str) -> None:
        self._emit(name, value, "Count", dims)

    def gauge(self, name: str, value: float, **dims: str) -> None:
        self._emit(name, value, "None", dims)

    def timing(self, name: str, ms: float, **dims: str) -> None:
        self._emit(name, ms, "Milliseconds", dims)

    def _emit(self, name: str, value: float, unit: Unit, dims: dict[str, str]) -> None:
        clean = {k: str(v) for k, v in list(dims.items())[:30] if v is not None}
        blob = {
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": self._namespace,
                        "Dimensions": [list(clean.keys())] if clean else [[]],
                        "Metrics": [{"Name": name, "Unit": unit}],
                    }
                ],
            },
            name: value,
            **clean,
        }
        _emf.info(json.dumps(blob, separators=(",", ":")))
