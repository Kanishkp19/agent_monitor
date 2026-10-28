"""Scoped repository understanding.

The model never receives the whole repository. It receives a compact map
plus the results of the four bounded read tools below, and `select_relevant`
does the filename/keyword scoring that decides which few files are worth
opening first.

Every operation is bounded (results, line counts, bytes) and every operation
runs through `FixtureWorkspace.resolve()`, so a model-supplied path can
neither escape the workspace nor name a secret file. Binaries are detected
by NUL bytes and refused rather than dumped into the prompt.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import re
from pathlib import Path

from agentshield.autopilot.schemas import ToolOutcome
from agentshield.autopilot.workspace import IGNORED_DIRS, FixtureWorkspace, is_secret_path

logger = logging.getLogger(__name__)

MAX_LIST_RESULTS = 200
MAX_SEARCH_HITS = 40
MAX_HIT_LINE_CHARS = 200
MAX_READ_LINES = 400
MAX_READ_CHARS = 16_000
MAX_MAP_ENTRIES = 300
BINARY_SNIFF_BYTES = 1024


class RepositoryExplorer:
    """Bounded, allowlisted read access to one fixture workspace."""

    def __init__(self, workspace: FixtureWorkspace) -> None:
        self._ws = workspace

    # ── tools ────────────────────────────────────────────────────────

    def repo_map(self) -> ToolOutcome:
        """Compact directory summary: files with sizes, capped entries."""
        entries: list[str] = []
        for path in sorted(self._iter_text_files()):
            rel = path.relative_to(self._ws.root).as_posix()
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            entries.append(f"{rel} ({size} B)")
            if len(entries) >= MAX_MAP_ENTRIES:
                entries.append(f"…[{MAX_MAP_ENTRIES}+ files, map truncated]")
                break
        body = (
            f"fixture: {self._ws.fixture_id} ({self._ws.manifest.language})\n"
            f"test command: {' '.join(self._ws.manifest.test_command)}\n"
            "files:\n" + "\n".join(entries)
        )
        return ToolOutcome(tool="repo_map", ok=True, output=body)

    def list_files(self, glob: str = "**/*", max_results: int = MAX_LIST_RESULTS) -> ToolOutcome:
        """Bounded glob listing. Ignored dirs and secret names never appear."""
        max_results = max(1, min(max_results, MAX_LIST_RESULTS))
        if ".." in glob or glob.startswith(("/", "~")):
            return ToolOutcome(tool="list_files", ok=False, error="invalid glob")
        files: list[str] = []
        for path in sorted(self._ws.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self._ws.root).as_posix()
            if self._ignored(rel):
                continue
            if not _glob_matches(rel, path.name, glob):
                continue
            files.append(rel)
            if len(files) >= max_results:
                return ToolOutcome(
                    tool="list_files",
                    ok=True,
                    output="\n".join(files),
                    truncated=True,
                )
        return ToolOutcome(
            tool="list_files",
            ok=True,
            output="\n".join(files) if files else "no matching files",
        )

    def search_text(
        self, pattern: str, paths: str = "", max_hits: int = MAX_SEARCH_HITS
    ) -> ToolOutcome:
        """Bounded text search over workspace text files.

        `pattern` is a Python regex; a malformed one is an error result for
        the model, not an exception for the loop. `paths` optionally
        constrains to files whose path contains that substring.
        """
        max_hits = max(1, min(max_hits, MAX_SEARCH_HITS))
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return ToolOutcome(tool="search_text", ok=False, error=f"invalid regex: {exc}")

        hits: list[str] = []
        searched = 0
        for path in self._iter_text_files():
            rel = path.relative_to(self._ws.root).as_posix()
            if paths and paths not in rel:
                continue
            searched += 1
            try:
                if path.stat().st_size > MAX_READ_CHARS:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    clipped = line.strip()[:MAX_HIT_LINE_CHARS]
                    hits.append(f"{rel}:{lineno}: {clipped}")
                    if len(hits) >= max_hits:
                        return ToolOutcome(
                            tool="search_text",
                            ok=True,
                            output="\n".join(hits),
                            truncated=True,
                        )
        if not hits:
            return ToolOutcome(
                tool="search_text",
                ok=True,
                output=f"no matches for {pattern!r} in {searched} file(s)",
            )
        return ToolOutcome(tool="search_text", ok=True, output="\n".join(hits))

    def read_file(self, path: str, start_line: int = 1, end_line: int = 0) -> ToolOutcome:
        """Bounded, line-numbered read of one workspace text file.

        Secret paths are refused here with an error result -- the executor
        does not rely on Gate 2 alone, and the refusal is worded so the
        model understands the boundary instead of probing it.
        """
        if is_secret_path(path):
            return ToolOutcome(
                tool="read_file",
                ok=False,
                error="blocked: secret file (executor rule, not negotiable)",
            )
        try:
            resolved = self._ws.resolve(path)
        except Exception as exc:  # PathRejected / WorkspaceError
            return ToolOutcome(tool="read_file", ok=False, error=str(exc))
        if not resolved.is_file():
            return ToolOutcome(tool="read_file", ok=False, error=f"no such file: {path}")
        if _is_binary(resolved):
            return ToolOutcome(tool="read_file", ok=False, error=f"binary file: {path}")
        if resolved.stat().st_size > MAX_READ_CHARS * 4:
            return ToolOutcome(tool="read_file", ok=False, error=f"file too large: {path}")

        try:
            lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            return ToolOutcome(tool="read_file", ok=False, error=f"unreadable: {exc}")

        start = max(1, start_line)
        end = end_line if end_line >= start else min(len(lines), start + MAX_READ_LINES - 1)
        end = min(end, start + MAX_READ_LINES - 1, len(lines))

        window = lines[start - 1 : end]
        numbered = [f"{lineno:>5}  {line[:250]}" for lineno, line in enumerate(window, start=start)]
        body = "\n".join(numbered)
        truncated = False
        if len(body) > MAX_READ_CHARS:
            body = body[:MAX_READ_CHARS] + "\n…[truncated]"
            truncated = True
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        header = f"{path} lines {start}-{end} of {len(lines)} sha256={digest}"
        return ToolOutcome(
            tool="read_file", ok=True, output=f"{header}\n{body}", truncated=truncated
        )

    # ── progressive context selection ────────────────────────────────

    def select_relevant(self, failure_output: str, limit: int = 5) -> list[str]:
        """Rank files by keyword overlap with the failure output.

        Deliberately simple: filename tokens, test-file names, and identifiers
        mentioned in the traceback. This is the 'cheap first' tier the plan
        asks for before any embedding machinery; it needs no network and no
        model call, and on these fixtures it finds the right file.
        """
        keywords = _keywords(failure_output)
        if not keywords:
            keywords = {"test", "app"}

        scored: list[tuple[int, str]] = []
        for path in self._iter_text_files():
            rel = path.relative_to(self._ws.root).as_posix()
            if self._ignored(rel):
                continue
            score = 0
            lowered_rel = rel.lower()
            for keyword in keywords:
                if keyword in lowered_rel:
                    score += 10
            try:
                if path.stat().st_size > MAX_READ_CHARS:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace").lower()
            except OSError:
                continue
            for keyword in keywords:
                score += min(text.count(keyword), 10)
            if score:
                scored.append((score, rel))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [rel for _, rel in scored[:limit]]

    # ── internals ────────────────────────────────────────────────────

    def _iter_text_files(self) -> list[Path]:
        files: list[Path] = []
        for path in sorted(self._ws.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self._ws.root).as_posix()
            if self._ignored(rel) or _is_binary(path):
                continue
            try:
                if self._ws.resolve(rel) != path.resolve():
                    continue
            except Exception as exc:
                logger.debug("skipping unsafe workspace file %s: %s", rel, exc)
                continue
            files.append(path)
        return files

    @staticmethod
    def _ignored(relative: str) -> bool:
        if any(part in IGNORED_DIRS for part in Path(relative).parts):
            return True
        return is_secret_path(relative)


def _glob_matches(relative: str, name: str, glob: str) -> bool:
    """Workspace glob semantics: `**/*` (the default) matches everything,
    including top-level files; a bare `*.py` matches at any depth; anything
    more specific is matched against the full relative path.
    """
    if glob in ("", "*", "**", "**/*"):
        return True
    if fnmatch.fnmatch(relative, glob):
        return True
    return fnmatch.fnmatch(relative, f"*/{glob}") or fnmatch.fnmatch(name, glob)


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\0" in handle.read(BINARY_SNIFF_BYTES)
    except OSError:
        return True


def _keywords(failure_output: str) -> set[str]:
    """Extract plausible identifiers from a pytest traceback.

    Module paths (`app/auth.py`), test names (`test_expired_token_is_rejected`)
    and camel/snake identifiers all split into lowercase tokens. Very short
    and very common tokens are dropped to keep the scoring meaningful.
    """
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_./]+", failure_output):
        raw = raw.strip("./")
        if raw.endswith(".py"):
            tokens.add(raw.lower())
        for part in re.split(r"[._/](?![0-9])", raw):
            if len(part) >= 4 and part not in {
                "test",
                "tests",
                "assert",
                "error",
                "failed",
                "failure",
                "none",
                "true",
                "false",
                "call",
            }:
                tokens.add(part.lower())
    return tokens
