"""The sandbox: git, tests, deploys, API calls, external fetch.

Everything here is simulated, seeded, and offline. Three of those properties
are security guarantees and one is a determinism guarantee, and they turn out
to be the same guarantee:

  * `external_fetch` never performs a real network request. It consults an
    allowlist and returns a canned response.
  * `deploy` never touches infrastructure.
  * `run_tests` produces pass or fail from a seeded draw biased by the
    employee's `mistake_probability`, so the same run always fails the same
    tests.

A simulation that could reach the network would be neither reproducible nor
safe to leave running.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from agentshield.domain.enums import Environment, ToolName
from agentshield.domain.models import ToolResult
from agentshield.sandbox.vfs import VirtualFileSystem
from agentshield.sim.seed_data import EXTERNAL_ALLOWLIST, protected_branches


@dataclass
class ExecutionContext:
    """What the sandbox needs to know about who is acting, and with what luck."""

    task_id: str
    repo: str
    environment: Environment
    mistake_probability: float = 0.04
    rng: random.Random | None = None

    def draw(self) -> random.Random:
        """Every draw is seeded. Never module-level `random`."""
        return self.rng or random.Random(hash(self.task_id) & 0xFFFFFFFF)


class Sandbox:
    def __init__(self, vfs: VirtualFileSystem) -> None:
        self._vfs = vfs

    async def execute(
        self, tool: ToolName, args: dict[str, Any], context: ExecutionContext
    ) -> ToolResult:
        handler = {
            ToolName.READ_FILE: self._read_file,
            ToolName.EDIT_FILE: self._edit_file,
            ToolName.RUN_TESTS: self._run_tests,
            ToolName.GIT_COMMIT: self._git_commit,
            ToolName.GIT_PUSH: self._git_push,
            ToolName.CALL_API: self._call_api,
            ToolName.DEPLOY: self._deploy,
            ToolName.EXTERNAL_FETCH: self._external_fetch,
        }.get(tool)

        if handler is None:
            return ToolResult(ok=False, error=f"no sandbox handler for {tool}", duration_ms=0)

        return await handler(args, context)

    # ── files ────────────────────────────────────────────────────────

    async def _read_file(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        repo = str(args.get("repo") or ctx.repo)
        path = str(args.get("path") or "")
        content = await self._vfs.read(repo, path)

        if content is None:
            return ToolResult(
                ok=False,
                error=f"no such file: {repo}:{path}",
                duration_ms=ctx.draw().randint(2, 12),
            )

        # Storage truncation. The full file is in the VFS; a tool result is a
        # message to a model, not an archive.
        return ToolResult(ok=True, output=content[:2000], duration_ms=ctx.draw().randint(3, 25))

    async def _edit_file(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        repo = str(args.get("repo") or ctx.repo)
        path = str(args.get("path") or "")
        diff = str(args.get("diff") or "")
        result = await self._vfs.apply_diff(repo, path, diff)
        verb = "created" if result["created"] else "updated"
        return ToolResult(
            ok=True,
            output=f"{verb} {repo}:{path} ({result['lines_changed']} lines)",
            duration_ms=ctx.draw().randint(8, 40),
        )

    # ── tests ────────────────────────────────────────────────────────

    async def _run_tests(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        """Seeded pass or fail, biased by the employee's mistake probability.

        A sloppy intern genuinely fails more often, which is what makes the
        sloppy decoy expensive without being malicious -- and what makes a
        detector that flags him a false positive worth counting.
        """
        rng = ctx.draw()
        repo = str(args.get("repo") or ctx.repo)
        suite = str(args.get("suite") or "unit")
        total = rng.randint(12, 60)

        failed = 0
        if rng.random() < ctx.mistake_probability * 4:
            failed = rng.randint(1, max(1, total // 8))

        duration = rng.randint(400, 4000)
        if failed:
            return ToolResult(
                ok=False,
                output=f"{repo} {suite}: {total - failed} passed, {failed} failed",
                error=f"{failed} test(s) failed",
                duration_ms=duration,
            )
        return ToolResult(ok=True, output=f"{repo} {suite}: {total} passed", duration_ms=duration)

    # ── git ──────────────────────────────────────────────────────────

    async def _git_commit(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        rng = ctx.draw()
        repo = str(args.get("repo") or ctx.repo)
        branch = str(args.get("branch") or "main")
        message = str(args.get("message") or "")
        sha = f"{rng.getrandbits(28):07x}"
        return ToolResult(
            ok=True,
            output=f"{repo} [{branch} {sha}] {message[:60]}",
            duration_ms=rng.randint(20, 120),
        )

    async def _git_push(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        rng = ctx.draw()
        repo = str(args.get("repo") or ctx.repo)
        branch = str(args.get("branch") or "main")
        protected = branch in protected_branches(repo)
        note = " (protected)" if protected else ""
        return ToolResult(
            ok=True,
            output=f"pushed {repo}@{branch}{note}",
            duration_ms=rng.randint(200, 1500),
        )

    # ── services ─────────────────────────────────────────────────────

    async def _call_api(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        rng = ctx.draw()
        service = str(args.get("service") or "internal")
        method = str(args.get("method") or "GET").upper()
        path = str(args.get("path") or "/")
        status = 200 if rng.random() > ctx.mistake_probability else 500
        return ToolResult(
            ok=status < 400,
            output=f"{method} {service}{path} -> {status}",
            error=None if status < 400 else f"upstream returned {status}",
            duration_ms=rng.randint(30, 900),
        )

    async def _deploy(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        """Simulated deploy with a latency draw. Nothing is provisioned."""
        rng = ctx.draw()
        repo = str(args.get("repo") or ctx.repo)
        environment = str(args.get("environment") or ctx.environment)
        # Production deploys take longer and fail more often, which is what
        # makes the approval feel like it was protecting something.
        base = 12_000 if environment == "production" else 4_000
        failed = rng.random() < ctx.mistake_probability * 2
        return ToolResult(
            ok=not failed,
            output=f"deployed {repo} to {environment}" if not failed else "",
            error=None if not failed else f"deploy to {environment} failed health checks",
            duration_ms=rng.randint(base, base * 3),
        )

    async def _external_fetch(self, args: dict[str, Any], ctx: ExecutionContext) -> ToolResult:
        """Never performs a real request.

        This is both a security property and a determinism one: a simulation
        that could reach the network would produce a different event stream on
        every run, and every number the detector reports would be noise.

        Gate 2 blocks non-allowlisted hosts before this is reached; the check
        here is defence in depth, for the case where this is called directly.
        """
        rng = ctx.draw()
        url = str(args.get("url") or "")
        host = url.split("//")[-1].split("/")[0].lower()
        allowed = any(host == a or host.endswith(f".{a}") for a in EXTERNAL_ALLOWLIST)

        if not allowed:
            return ToolResult(
                ok=False,
                error=f"host not on the outbound allowlist: {host}",
                duration_ms=rng.randint(1, 5),
            )

        return ToolResult(
            ok=True,
            output=f"200 OK from {host} (canned response; no request was made)",
            duration_ms=rng.randint(50, 600),
        )
