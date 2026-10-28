"""Bounded, hash-checked edits to one disposable workspace."""

from __future__ import annotations

import difflib
import hashlib
import os
import tempfile
from pathlib import Path

from agentshield.autopilot.schemas import PatchArgs
from agentshield.autopilot.workspace import FixtureWorkspace, PathRejected, _is_ignored

MAX_CHANGED_LINES = 120
MAX_FILE_BYTES = 64_000


class PatchRejected(ValueError):
    pass


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def diff_from_snapshot(before: dict[str, str], workspace: FixtureWorkspace) -> str:
    after = workspace.snapshot()
    parts: list[str] = []
    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name, ""), after.get(name, "")
        if old != new:
            parts.extend(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{name}",
                    tofile=f"b/{name}",
                )
            )
    return "".join(parts)


def apply_patch(workspace: FixtureWorkspace, args: PatchArgs) -> str:
    """Validate every edit before replacing any file; restore originals on write failure."""
    prepared: list[tuple[Path, bytes, bytes]] = []
    seen: set[Path] = set()
    changed_lines = 0
    for edit in args.edits:
        try:
            path = workspace.resolve(edit.path)
        except PathRejected as exc:
            raise PatchRejected(str(exc)) from exc
        if path in seen or _is_ignored(Path(edit.path)) or not path.is_file() or path.is_symlink():
            raise PatchRejected(f"path is not an editable regular file: {edit.path}")
        seen.add(path)
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES or b"\0" in raw:
            raise PatchRejected(f"file is too large or binary: {edit.path}")
        try:
            original = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PatchRejected(f"file is not UTF-8: {edit.path}") from exc
        if sha256(original) != edit.expected_sha256:
            raise PatchRejected(f"stale file hash: {edit.path}")
        if original.count(edit.old) != 1:
            raise PatchRejected(f"old text must occur exactly once: {edit.path}")
        updated = original.replace(edit.old, edit.new, 1)
        if len(updated.encode("utf-8")) > MAX_FILE_BYTES:
            raise PatchRejected(f"result is too large: {edit.path}")
        changed_lines += len(edit.old.splitlines()) + len(edit.new.splitlines())
        prepared.append((path, raw, updated.encode("utf-8")))
    if changed_lines > MAX_CHANGED_LINES:
        raise PatchRejected("patch changes too many lines")

    written: list[tuple[Path, bytes]] = []
    try:
        for path, old, new in prepared:
            # Verify again immediately before each replacement.
            if path.is_symlink() or path.read_bytes() != old:
                raise PatchRejected(f"file changed during patch: {path.name}")
            _replace(path, new)
            written.append((path, old))
    except Exception:
        for path, old in reversed(written):
            _replace(path, old)
        raise
    return "\n".join(f"edited {path.relative_to(workspace.root)}" for path, _, _ in prepared)


def _replace(path: Path, data: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".autopilot-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.chmod(name, path.stat().st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
