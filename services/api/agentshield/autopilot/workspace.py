"""Disposable fixture workspaces.

An Autopilot job never touches a user repository. It works on a throwaway
copy of a whitelisted fixture, created in `.data/autopilot-workspaces/`,
and the copy is deleted when the job ends.

`resolve()` is the one path through which any tool may touch the filesystem.
It re-derives containment from the *resolved* path -- after symlink
expansion -- so `..`, absolute paths, and symlink escapes all fail the same
way. This is the executor-side guarantee that holds even if every upstream
gate were removed: the explorer and patcher cannot name a file outside the
workspace because this method refuses to hand them one.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path

from agentshield.autopilot.schemas import FixtureManifest
from agentshield.governance.gate2 import SECRET_PATH_PATTERNS

logger = logging.getLogger(__name__)

MANIFEST_NAME = "fixture.json"


class WorkspaceError(Exception):
    """A workspace could not be created, or a path rejected."""


class UnknownFixture(WorkspaceError):
    """The requested fixture id is not in the whitelist."""


class PathRejected(WorkspaceError):
    """A relative path escaped, or attempted to escape, the workspace."""


class FixtureWorkspace:
    """One disposable copy of one fixture. Create via `WorkspaceManager`."""

    def __init__(self, *, fixture_id: str, manifest: FixtureManifest, root: Path) -> None:
        self.fixture_id = fixture_id
        self.manifest = manifest
        self.root = root

    # ── path safety ──────────────────────────────────────────────────

    def resolve(self, relative: str) -> Path:
        """Map a model-supplied path onto a real path inside `root`.

        Every filesystem touch in the engine goes through here. Symlinks are
        resolved before containment is checked, so a symlink planted inside
        the workspace pointing at `/etc/passwd` resolves outside and is
        rejected -- the check is on where the file *is*, not where it is
        claimed to be.
        """
        if not relative or relative.strip() in ("", "."):
            raise PathRejected("empty path")
        candidate = Path(relative)
        if candidate.is_absolute() or relative.startswith("~"):
            raise PathRejected(f"absolute paths are not permitted: {relative!r}")
        if ".." in candidate.parts:
            raise PathRejected(f"parent traversal is not permitted: {relative!r}")
        if is_secret_path(candidate.as_posix()):
            raise PathRejected(f"secret paths are never readable: {relative!r}")
        current = self.root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise PathRejected(f"symlinks are not permitted: {relative!r}")
        resolved = (self.root / candidate).resolve()
        if not (resolved == self.root or self.root in resolved.parents):
            raise PathRejected(f"path escapes the workspace: {relative!r}")
        if resolved.is_symlink() or resolved.is_file():
            # Re-check after symlink expansion: a link inside the workspace
            # that lands on a secret-named file outside it is still refused.
            try:
                rel_resolved = resolved.relative_to(self.root)
            except ValueError:
                raise PathRejected(f"path escapes the workspace: {relative!r}") from None
            if is_secret_path(rel_resolved.as_posix()):
                raise PathRejected(f"secret paths are never readable: {relative!r}")
        return resolved

    def exists(self, relative: str) -> bool:
        try:
            return self.resolve(relative).exists()
        except PathRejected:
            return False

    def is_secret_path(self, relative: str) -> bool:
        """Executor-side secret rule, independent of any policy engine.

        Uses the same pattern list as Gate 2, evaluated here in the code
        that would otherwise open the file.
        """
        return is_secret_path(relative)

    # ── snapshot and diff ────────────────────────────────────────────

    def snapshot(self) -> dict[str, str]:
        """Content of every text file, taken before the first edit.

        The diff engine compares against this, so `git` is not a runtime
        dependency of the sandbox and the snapshot cannot be tampered with
        by a patch.
        """
        files: dict[str, str] = {}
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or _is_ignored(path.relative_to(self.root)):
                continue
            try:
                self.resolve(path.relative_to(self.root).as_posix())
                files[path.relative_to(self.root).as_posix()] = path.read_text(
                    encoding="utf-8"
                )
            except (UnicodeDecodeError, OSError, PathRejected):
                continue
        return files


class WorkspaceManager:
    """Creates and cleans fixture workspaces. One per engine instance."""

    def __init__(self, *, fixtures_dir: Path, workspaces_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir
        self._workspaces_dir = workspaces_dir

    def available_fixtures(self) -> list[FixtureManifest]:
        """Every whitelisted fixture, sorted by id."""
        manifests: list[FixtureManifest] = []
        if not self._fixtures_dir.exists():
            return manifests
        for manifest_path in sorted(self._fixtures_dir.glob(f"*/{MANIFEST_NAME}")):
            try:
                manifest = _load_manifest(manifest_path)
                if manifest.fixture_id != manifest_path.parent.name:
                    raise WorkspaceError("fixture ID must match its directory")
            except (WorkspaceError, ValueError) as exc:
                logger.warning("skipping invalid fixture manifest %s: %s", manifest_path, exc)
                continue
            manifests.append(manifest)
        return manifests

    def manifest_for(self, fixture_id: str) -> FixtureManifest:
        for manifest in self.available_fixtures():
            if manifest.fixture_id == fixture_id:
                return manifest
        raise UnknownFixture(
            f"fixture {fixture_id!r} is not whitelisted; "
            f"available: {[m.fixture_id for m in self.available_fixtures()]}"
        )

    def create(self, fixture_id: str) -> FixtureWorkspace:
        """Copy a whitelisted fixture into a fresh disposable directory.

        The manifest itself is excluded from the copy: it is engine
        configuration, not repository content the model should see or edit.
        """
        manifest = self.manifest_for(fixture_id)
        source = self._fixtures_dir / fixture_id
        if source.is_symlink():
            raise WorkspaceError("fixture directory is a symlink")
        if source.resolve().parent != self._fixtures_dir.resolve():
            raise WorkspaceError("fixture directory escapes whitelist")
        for path in source.rglob("*"):
            if path.is_symlink():
                raise WorkspaceError("fixture contains a symlink")
        self._workspaces_dir.mkdir(parents=True, exist_ok=True)
        target = Path(
            tempfile.mkdtemp(prefix=f"{fixture_id}-", dir=self._workspaces_dir)
        )
        target.chmod(0o755)  # the unprivileged test container needs read access
        shutil.copytree(
            source,
            target,
            ignore=shutil.ignore_patterns(MANIFEST_NAME, "__pycache__", "*.pyc", ".git"),
            dirs_exist_ok=True,
        )
        logger.info(
            "fixture workspace created",
            extra={"fixture": fixture_id, "workspace": str(target)},
        )
        return FixtureWorkspace(fixture_id=fixture_id, manifest=manifest, root=target)

    @staticmethod
    def cleanup(workspace: FixtureWorkspace) -> None:
        shutil.rmtree(workspace.root, ignore_errors=True)
        logger.info("fixture workspace removed", extra={"fixture": workspace.fixture_id})


def _load_manifest(path: Path) -> FixtureManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return FixtureManifest.model_validate(data)


IGNORED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }
)

# A file whose *name* matches one of these is never listed, read, searched,
# or patched by the engine, whoever asks. Fake secrets stay in fixtures
# precisely so this rule is exercised on every run.
IGNORED_FILE_SUFFIXES = (".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip")


def is_secret_path(relative: str) -> bool:
    """Executor-side secret rule over the Gate 2 pattern list.

    Duplicated intentionally as a *constant* import (not a call into the
    gate): the executor must keep working if the gate service is unavailable.
    """
    if not relative:
        return False
    lowered = relative.lower()
    return any(marker in lowered for marker in SECRET_PATH_PATTERNS)


def _is_ignored(relative: Path) -> bool:
    if any(part in IGNORED_DIRS for part in relative.parts):
        return True
    name = relative.name.lower()
    if name.endswith(IGNORED_FILE_SUFFIXES):
        return True
    return is_secret_path(relative.as_posix())
