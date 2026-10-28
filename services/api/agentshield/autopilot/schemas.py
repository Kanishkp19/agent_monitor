"""Typed contracts for the Autopilot engine.

Everything that crosses a boundary -- fixture manifests, tool actions,
explorer results, test outcomes, job state -- is a pydantic model here, so
the runner, the API routes and the tests share one vocabulary.

The tool names below are the *Autopilot* toolset, deliberately separate from
`domain.enums.ToolName` (the simulated office's tools). The simulated tools
describe actions against imaginary repos; these describe actions against a
real disposable workspace, with different safety constraints. One is a
theatre stage, the other is a workshop -- conflating them would let a policy
written for the stage govern the workshop.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AutopilotTool(StrEnum):
    """The closed toolset the model may propose. Nothing else executes."""

    LIST_FILES = "list_files"
    SEARCH_TEXT = "search_text"
    READ_FILE = "read_file"
    REPO_MAP = "repo_map"
    APPLY_PATCH = "apply_patch"
    RUN_TESTS = "run_tests"
    FINISH = "finish"
    REJECTED = "rejected"


class FixtureManifest(BaseModel):
    """What `infra/fixtures/<id>/fixture.json` declares about a fixture."""

    model_config = ConfigDict(extra="ignore")

    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str
    description: str = ""
    language: Literal["python"] = "python"
    test_command: list[str] = Field(default_factory=lambda: ["python", "-m", "pytest", "-q"])
    timeout_seconds: int = Field(60, ge=5, le=300)
    suggested_goal: str = ""
    contains_injection: bool = False


class ToolAction(BaseModel):
    """One validated tool proposal, exactly as it will be governed and run."""

    model_config = ConfigDict(frozen=True)

    tool: AutopilotTool
    args: dict[str, Any] = Field(default_factory=dict)
    call_id: str = ""

    def summary(self) -> str:
        """A stable human-readable name for what is about to happen."""
        if self.tool is AutopilotTool.READ_FILE:
            return f"read_file:{self.args.get('path', '')}"
        if self.tool is AutopilotTool.LIST_FILES:
            return f"list_files:{self.args.get('glob', '*')}"
        if self.tool is AutopilotTool.SEARCH_TEXT:
            return f"search_text:{self.args.get('pattern', '')!r}"
        if self.tool is AutopilotTool.APPLY_PATCH:
            return f"apply_patch:{len(self.args.get('edits', []))} file(s)"
        if self.tool is AutopilotTool.RUN_TESTS:
            return "run_tests"
        if self.tool is AutopilotTool.FINISH:
            return "finish"
        return str(self.tool)


class ToolOutcome(BaseModel):
    """What actually happened when an authorized action executed (or not)."""

    tool: AutopilotTool
    ok: bool
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    truncated: bool = False


class TestRunResult(BaseModel):
    """Exit-code-level truth from a real pytest run. Never synthesized."""

    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    command: list[str] = Field(default_factory=list)
    summary_line: str = ""

    def preview(self, chars: int = 4000) -> str:
        """Bounded combined output for the model's context window."""
        combined = (self.stdout + "\n" + self.stderr).strip()
        if len(combined) > chars:
            return combined[:chars] + "\n…[truncated]"
        return combined


class JobStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    EXPLORING = "exploring"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AutopilotJobSpec(BaseModel):
    """Input contract for one autopilot run."""

    fixture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    goal: str = Field(min_length=1, max_length=2000)
    max_steps: int = Field(20, ge=3, le=20)
    max_repair_rounds: int = Field(3, ge=1, le=3)


class FileEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=240)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    old: str = Field(min_length=1, max_length=12_000)
    new: str = Field(max_length=12_000)


class PatchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edits: list[FileEdit] = Field(min_length=1, max_length=3)


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=240)
    start_line: int = Field(1, ge=1)
    end_line: int = Field(0, ge=0)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: str = Field(min_length=1, max_length=200)
    paths: str = Field("", max_length=240)
    max_hits: int = Field(40, ge=1, le=40)


class ListArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    glob: str = Field("**/*", max_length=240)
    max_results: int = Field(200, ge=1, le=200)


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
