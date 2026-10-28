"""Autopilot: the live coding engine.

A real Nemotron agent that reads actual files, patches them, and runs real
tests inside a disposable fixture workspace -- under the same Gate 1 / Gate 2
governance and the same telemetry emitter as the simulation.

`autopilot/` is domain-level: it depends on ports and governance, never on
`adapters/` (enforced by `tests/test_architecture.py`). The composition root
in `container.py` injects the live provider.
"""
