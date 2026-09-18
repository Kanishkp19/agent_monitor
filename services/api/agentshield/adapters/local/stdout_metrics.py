"""Stdout implementation of MetricsPort, emitting CloudWatch EMF.

The local adapter prints the *same* Embedded Metric Format JSON that the AWS
adapter sends to CloudWatch. A dashboard or a log query written against one
works against the other, which is the whole reason for emitting a structured
blob rather than a friendly line.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Literal

Unit = Literal["Count", "Milliseconds", "None"]


class StdoutMetrics:
    def __init__(self, namespace: str = "AgentShield", stream: Any = None) -> None:
        self._namespace = namespace
        self._stream = stream if stream is not None else sys.stdout

    def count(self, name: str, value: float = 1, **dims: str) -> None:
        self._emit(name, value, "Count", dims)

    def gauge(self, name: str, value: float, **dims: str) -> None:
        self._emit(name, value, "None", dims)

    def timing(self, name: str, ms: float, **dims: str) -> None:
        self._emit(name, ms, "Milliseconds", dims)

    def _emit(self, name: str, value: float, unit: Unit, dims: dict[str, str]) -> None:
        # EMF caps a dimension set at 30 keys and requires string values.
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
        print(json.dumps(blob, separators=(",", ":")), file=self._stream)
