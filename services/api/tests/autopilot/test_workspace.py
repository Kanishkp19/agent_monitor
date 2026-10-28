"""Autopilot fixture workspaces: creation, path safety, snapshot."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentshield.autopilot.workspace import (
    PathRejected,
    UnknownFixture,
    WorkspaceManager,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
FIXTURES = REPO_ROOT / "infra" / "fixtures"


@pytest.fixture()
def manager(tmp_path: Path) -> WorkspaceManager:
    return WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path / "ws")


def test_fixtures_are_whitelisted(manager: WorkspaceManager) -> None:
    available = {m.fixture_id for m in manager.available_fixtures()}
    assert "buggy-auth" in available
    assert "prompt-injection" in available


def test_unknown_fixture_is_refused(manager: WorkspaceManager) -> None:
    with pytest.raises(UnknownFixture):
        manager.create("not-a-real-fixture")


def test_workspace_is_a_disposable_copy(manager: WorkspaceManager) -> None:
    ws = manager.create("buggy-auth")
    try:
        assert (ws.root / "app" / "auth.py").is_file()
        # the manifest is engine config, not repo content
        assert not (ws.root / "fixture.json").exists()
    finally:
        manager.cleanup(ws)
    assert not ws.root.exists(), "cleanup must remove the disposable copy"


def test_concurrent_copies_are_isolated(manager: WorkspaceManager) -> None:
    first = manager.create("buggy-auth")
    second = manager.create("buggy-auth")
    try:
        source = first.root / "app" / "auth.py"
        source.write_text(source.read_text().replace("now >= expires_at", "now < expires_at"))
        assert "now >= expires_at" in (second.root / "app" / "auth.py").read_text()
    finally:
        manager.cleanup(first)
        manager.cleanup(second)


def test_resolve_rejects_absolute_and_traversal(manager: WorkspaceManager) -> None:
    ws = manager.create("buggy-auth")
    try:
        with pytest.raises(PathRejected):
            ws.resolve("/etc/passwd")
        with pytest.raises(PathRejected):
            ws.resolve("../../etc/passwd")
        with pytest.raises(PathRejected):
            ws.resolve("app/../../../../../etc/passwd")
        with pytest.raises(PathRejected):
            ws.resolve("")
        assert ws.resolve("app/auth.py").is_file()
    finally:
        manager.cleanup(ws)


def test_resolve_rejects_symlink_escape(manager: WorkspaceManager) -> None:
    ws = manager.create("buggy-auth")
    try:
        link = ws.root / "innocent"
        link.symlink_to("/etc")
        with pytest.raises(PathRejected):
            ws.resolve("innocent/passwd")
    finally:
        manager.cleanup(ws)


def test_secret_paths_are_recognised_executorside(manager: WorkspaceManager) -> None:
    ws = manager.create("prompt-injection")
    try:
        assert ws.is_secret_path(".env.production")
        assert ws.is_secret_path("config/server.pem")
        assert not ws.is_secret_path("app/greet.py")
        assert not ws.exists(".env.production"), "secret file must be excluded from exists()"
    finally:
        manager.cleanup(ws)


def test_snapshot_captures_workspace_text_files(manager: WorkspaceManager) -> None:
    ws = manager.create("buggy-auth")
    try:
        snapshot = ws.snapshot()
        assert "app/auth.py" in snapshot
        assert "tests/test_auth.py" in snapshot
        assert "now >= expires_at" in snapshot["app/auth.py"]
    finally:
        manager.cleanup(ws)
