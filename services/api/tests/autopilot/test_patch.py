from __future__ import annotations

from pathlib import Path

import pytest

from agentshield.autopilot.patch import PatchRejected, apply_patch, diff_from_snapshot, sha256
from agentshield.autopilot.schemas import PatchArgs
from agentshield.autopilot.workspace import PathRejected, WorkspaceManager

FIXTURES = Path(__file__).resolve().parents[4] / "infra" / "fixtures"


@pytest.fixture()
def workspace(tmp_path: Path):  # type: ignore[no-untyped-def]
    manager = WorkspaceManager(fixtures_dir=FIXTURES, workspaces_dir=tmp_path)
    ws = manager.create("buggy-auth")
    yield ws
    manager.cleanup(ws)


def _edit(path: str, original: str, old: str, new: str) -> dict[str, str]:
    return {"path": path, "expected_sha256": sha256(original), "old": old, "new": new}


def test_real_patch_has_diff_and_source_is_untouched(workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace.root / "app" / "auth.py"
    original = path.read_text()
    before = workspace.snapshot()
    args = PatchArgs(
        edits=[_edit("app/auth.py", original, "now >= expires_at", "now < expires_at")]
    )
    apply_patch(workspace, args)
    assert path.read_text() != original
    assert "-        return now >= expires_at" in diff_from_snapshot(before, workspace)
    assert (FIXTURES / "buggy-auth" / "app" / "auth.py").read_text() == original


def test_invalid_second_edit_has_no_partial_write(workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace.root / "app" / "auth.py"
    original = path.read_text()
    edits = [
        _edit("app/auth.py", original, "now >= expires_at", "now < expires_at"),
        _edit("tests/test_auth.py", "wrong version", "a", "b"),
    ]
    with pytest.raises(PatchRejected):
        apply_patch(workspace, PatchArgs(edits=edits))
    assert path.read_text() == original


def test_stale_hash_and_symlink_are_rejected(workspace) -> None:  # type: ignore[no-untyped-def]
    path = workspace.root / "app" / "auth.py"
    original = path.read_text()
    with pytest.raises(PatchRejected):
        apply_patch(
            workspace, PatchArgs(edits=[_edit("app/auth.py", "stale", "now >= expires_at", "x")])
        )
    (workspace.root / "alias.py").symlink_to(path)
    with pytest.raises(PathRejected):
        workspace.resolve("alias.py")
    assert path.read_text() == original
