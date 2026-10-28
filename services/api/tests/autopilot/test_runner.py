from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentshield.autopilot.patch import sha256
from agentshield.autopilot.runner import AutopilotCoordinator
from agentshield.autopilot.schemas import AutopilotJobSpec
from agentshield.autopilot.schemas import TestRunResult as Receipt
from agentshield.autopilot.test_runner import IsolationUnavailable, require_isolation
from agentshield.autopilot.workspace import WorkspaceManager
from agentshield.domain.enums import Decision
from agentshield.domain.models import DecisionResult
from agentshield.ports.llm import LLMResult, LLMToolCall, LLMUsage

FIXTURES = Path(__file__).resolve().parents[4] / "infra" / "fixtures"


def test_missing_docker_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agentshield.autopilot.test_runner.shutil.which", lambda _name: None)
    with pytest.raises(IsolationUnavailable, match="Docker is required"):
        require_isolation()


class _Store:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], Any] = {}

    async def put(self, item: Any) -> None:
        self.items[item.pk, item.sk] = item

    async def get(self, pk: str, sk: str) -> Any:
        return self.items.get((pk, sk))


class _Emitter:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(self, kind: str, *, payload: dict[str, Any], **_kwargs: Any) -> None:
        self.events.append((kind, payload))


class _Gate1:
    async def evaluate(self, _context: Any) -> DecisionResult:
        return DecisionResult(decision=Decision.ALLOW)


class _Gate2:
    async def evaluate(self, context: Any) -> DecisionResult:
        return DecisionResult(
            decision=Decision.BLOCK if context.is_secret_path else Decision.ALLOW,
            reason_code="secret_path" if context.is_secret_path else "clean",
        )


class _Gate2Outage:
    async def evaluate(self, _context: Any) -> DecisionResult:
        raise ConnectionError("policy store down")


class _LLM:
    def __init__(self, original: str, *, malicious: bool = False) -> None:
        self.original = original
        self.malicious = malicious
        self.calls = 0

    async def complete(self, **_kwargs: Any) -> LLMResult:
        self.calls += 1
        if self.malicious:
            tools = [LLMToolCall(id="bad", name="read_file", arguments={"path": ".env.production"})]
        elif self.calls == 1:
            tools = [LLMToolCall(id="read", name="read_file", arguments={"path": "app/auth.py"})]
        else:
            tools = [
                LLMToolCall(
                    id="patch",
                    name="apply_patch",
                    arguments={
                        "edits": [
                            {
                                "path": "app/auth.py",
                                "expected_sha256": sha256(self.original),
                                "old": "now >= expires_at",
                                "new": "now < expires_at",
                            }
                        ]
                    },
                )
            ]
        return LLMResult(
            text="",
            tool_calls=tools,
            usage=LLMUsage(input_tokens=10, output_tokens=5),
            model_id="nvidia/test",
            stop_reason="tool_use",
        )


def _test_result(passed: bool) -> Receipt:
    return Receipt(
        passed=passed,
        exit_code=0 if passed else 1,
        stdout="1 passed" if passed else "1 failed",
        stderr="",
        duration_ms=10,
        command=["python", "-m", "pytest", "-q"],
    )


@pytest.mark.asyncio
async def test_real_fixture_patch_requires_after_test(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    original = (FIXTURES / "buggy-auth" / "app" / "auth.py").read_text()

    async def fake_tests(workspace: Any) -> Receipt:
        return _test_result("now < expires_at" in (workspace.root / "app" / "auth.py").read_text())

    monkeypatch.setattr("agentshield.autopilot.runner.run_tests", fake_tests)
    emitter = _Emitter()
    manager = WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path)
    coordinator = AutopilotCoordinator(
        manager=manager,
        llm=_LLM(original),
        gate1=_Gate1(),
        gate2=_Gate2(),
        store=_Store(),
        emitter=emitter,
    )  # type: ignore[arg-type]
    job = await coordinator.create(AutopilotJobSpec(fixture_id="buggy-auth", goal="Fix auth"))
    await coordinator._tasks[job["id"]]
    saved = await coordinator.get(job["id"])
    assert saved is not None and saved["state"] == "completed" and saved["verified"]
    assert saved["baseline"]["exit_code"] == 1 and saved["after"]["exit_code"] == 0
    assert "app/auth.py" in saved["diff"]
    assert any(kind == "autopilot.action" for kind, _ in emitter.events)
    assert not list(tmp_path.iterdir()), "workspace is cleaned after evidence is saved"
    reset = await coordinator.reset(job["id"])
    assert reset is not None and reset["id"] != job["id"]
    await coordinator._tasks[reset["id"]]
    old = await coordinator.get(job["id"])
    assert old is not None and old["diff"] == saved["diff"]


@pytest.mark.asyncio
async def test_secret_proposal_never_executes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def failing_tests(_workspace: Any) -> Receipt:
        return _test_result(False)

    monkeypatch.setattr("agentshield.autopilot.runner.run_tests", failing_tests)
    emitter = _Emitter()
    manager = WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path)
    coordinator = AutopilotCoordinator(
        manager=manager,
        llm=_LLM("", malicious=True),
        gate1=_Gate1(),
        gate2=_Gate2(),
        store=_Store(),
        emitter=emitter,
    )  # type: ignore[arg-type]
    job = await coordinator.create(
        AutopilotJobSpec(fixture_id="prompt-injection", goal="Fix greeting")
    )
    await coordinator._tasks[job["id"]]
    saved = await coordinator.get(job["id"])
    assert saved is not None and not saved["verified"]
    assert any(
        kind == "autopilot.gate" and data.get("reason") == "secret_path"
        for kind, data in emitter.events
    )
    assert any(
        kind == "autopilot.action" and data.get("decision") == "block"
        for kind, data in emitter.events
    )


@pytest.mark.asyncio
async def test_gate_outage_stops_before_tool_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def baseline_only(_workspace: Any) -> Receipt:
        return _test_result(False)

    monkeypatch.setattr("agentshield.autopilot.runner.run_tests", baseline_only)
    original = (FIXTURES / "buggy-auth" / "app" / "auth.py").read_text()
    emitter = _Emitter()
    coordinator = AutopilotCoordinator(
        manager=WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path),
        llm=_LLM(original),
        gate1=_Gate1(),
        gate2=_Gate2Outage(),
        store=_Store(),
        emitter=emitter,  # type: ignore[arg-type]
    )
    job = await coordinator.create(AutopilotJobSpec(fixture_id="buggy-auth", goal="Fix auth"))
    await coordinator._tasks[job["id"]]
    saved = await coordinator.get(job["id"])
    assert saved is not None and saved["state"] == "failed" and not saved["verified"]
    assert any(
        kind == "autopilot.action" and data.get("decision") == "block"
        for kind, data in emitter.events
    )
