"""Autopilot repository explorer: bounds, secret exclusion, relevance."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentshield.autopilot.context import (
    MAX_LIST_RESULTS,
    MAX_SEARCH_HITS,
    RepositoryExplorer,
)
from agentshield.autopilot.schemas import AutopilotTool
from agentshield.autopilot.workspace import WorkspaceManager

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "infra" / "fixtures"


@pytest.fixture()
def buggy_auth(tmp_path: Path):  # type: ignore[no-untyped-def]
    manager = WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path / "ws")
    ws = manager.create("buggy-auth")
    try:
        yield ws
    finally:
        manager.cleanup(ws)


@pytest.fixture()
def injection(tmp_path: Path):  # type: ignore[no-untyped-def]
    manager = WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path / "ws")
    ws = manager.create("prompt-injection")
    try:
        yield ws
    finally:
        manager.cleanup(ws)


def test_repo_map_is_compact_and_bounded(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(buggy_auth).repo_map()
    assert outcome.ok
    assert outcome.tool == AutopilotTool.REPO_MAP
    assert "app/auth.py" in outcome.output
    assert "tests/test_auth.py" in outcome.output
    assert "python -m pytest" in outcome.output
    assert len(outcome.output) < 4000


def test_list_files_excludes_ignored_and_secrets(injection) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(injection).list_files()
    assert ".env.production" not in outcome.output, "secret must never be listed"
    assert "app/greet.py" in outcome.output
    assert "README.md" in outcome.output


def test_list_files_respects_max_results(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(buggy_auth).list_files(max_results=2)
    assert outcome.truncated
    assert len(outcome.output.splitlines()) == 2
    assert MAX_LIST_RESULTS == 200  # bound is not configurable into absurdity


def test_read_file_returns_numbered_lines(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(buggy_auth).read_file("app/auth.py")
    assert outcome.ok
    assert "1" in outcome.output.splitlines()[0]
    assert "SessionStore" in outcome.output


def test_read_file_refuses_secret_paths(injection) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(injection).read_file(".env.production")
    assert not outcome.ok
    assert "blocked" in outcome.error
    assert "FAKE_NOT_A_REAL_SECRET" not in (outcome.output + outcome.error)


def test_read_file_refuses_traversal_and_missing(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    explorer = RepositoryExplorer(buggy_auth)
    assert not explorer.read_file("../agentshield/config.py").ok
    assert not explorer.read_file("app/nope.py").ok


def test_search_text_is_line_numbered_and_bounded(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    explorer = RepositoryExplorer(buggy_auth)
    outcome = explorer.search_text("expires_at")
    assert outcome.ok
    assert "app/auth.py:" in outcome.output
    assert len(outcome.output.splitlines()) <= MAX_SEARCH_HITS


def test_search_text_reports_bad_regex(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    outcome = RepositoryExplorer(buggy_auth).search_text("([unclosed")
    assert not outcome.ok
    assert "invalid regex" in outcome.error


def test_select_relevant_finds_auth_from_failure_output(buggy_auth) -> None:  # type: ignore[no-untyped-def]
    """The M2 exit gate: the failing-test output alone points at auth.py."""
    failure = (
        "FAILED tests/test_auth.py::test_expired_token_is_rejected - "
        "assert True is False\n"
        "FAILED tests/test_auth.py::test_fresh_token_is_accepted - "
        "assert False is True\n"
        "E       assert 1005 >= 1360"
    )
    relevant = RepositoryExplorer(buggy_auth).select_relevant(failure)
    assert relevant, "must rank at least one file"
    assert relevant[0].endswith("auth.py"), f"auth.py should rank first, got {relevant}"


def test_select_relevant_never_suggests_secrets(injection) -> None:  # type: ignore[no-untyped-def]
    relevant = RepositoryExplorer(injection).select_relevant("env production secret credentials")
    assert all(".env" not in rel for rel in relevant)
