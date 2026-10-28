"""Run the fixture's fixed pytest command inside a disposable Docker container."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
import uuid

from agentshield.autopilot.schemas import TestRunResult
from agentshield.autopilot.workspace import FixtureWorkspace

IMAGE = "agentshield-autopilot-pytest:2026-10"
COMMAND = ["python", "-m", "pytest", "-q"]
MAX_OUTPUT = 256_000


class IsolationUnavailable(RuntimeError):
    pass


def require_isolation() -> None:
    if shutil.which("docker") is None:
        raise IsolationUnavailable("Docker is required for Autopilot test execution")
    for args in (
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        ["docker", "image", "inspect", IMAGE],
    ):
        try:
            result = subprocess.run(  # noqa: S603 - fixed Docker CLI arguments only
                args, capture_output=True, timeout=5, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise IsolationUnavailable(f"Docker is unavailable: {exc}") from exc
        if result.returncode != 0:
            raise IsolationUnavailable(
                "Docker daemon or pinned Autopilot image unavailable; "
                "build with: docker build -t " + IMAGE + " infra/autopilot"
            )


async def run_tests(workspace: FixtureWorkspace) -> TestRunResult:
    require_isolation()
    if workspace.manifest.test_command != COMMAND:
        raise IsolationUnavailable("fixture test command is not allowlisted")
    started = time.monotonic()
    container_name = f"agentshield-test-{uuid.uuid4().hex}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--pids-limit",
        "64",
        "--cpus",
        "1",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=32m",  # noqa: S108 - private container tmpfs
        "--mount",
        f"type=bind,src={workspace.root},dst=/workspace,readonly",
        "--workdir",
        "/workspace",
        "--env",
        "HOME=/tmp",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        "--env",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
        IMAGE,
        *COMMAND,
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    assert process.stdout is not None and process.stderr is not None

    async def read_limited(stream: asyncio.StreamReader) -> tuple[bytes, bool]:
        chunks: list[bytes] = []
        length = 0
        truncated = False
        while chunk := await stream.read(8192):
            if length < MAX_OUTPUT:
                kept = chunk[: MAX_OUTPUT - length]
                chunks.append(kept)
                length += len(kept)
                if len(kept) < len(chunk):
                    truncated = True
            else:
                truncated = True
        return b"".join(chunks), truncated

    stdout_task = asyncio.create_task(read_limited(process.stdout))
    stderr_task = asyncio.create_task(read_limited(process.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=workspace.manifest.timeout_seconds)
    except (TimeoutError, asyncio.CancelledError) as exc:
        timed_out = isinstance(exc, TimeoutError)
        process.kill()
        await process.wait()
        cleanup = await asyncio.create_subprocess_exec(
            "docker",
            "rm",
            "-f",
            container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await cleanup.wait()
        if not timed_out:
            raise
    stdout, stdout_truncated = await stdout_task
    stderr, stderr_truncated = await stderr_task
    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")
    if stdout_truncated:
        out += "\n[output truncated]"
    if stderr_truncated:
        err += "\n[output truncated]"
    summary = next(
        (line for line in reversed(out.splitlines()) if "passed" in line or "failed" in line),
        "",
    )
    return TestRunResult(
        passed=process.returncode == 0 and not timed_out,
        exit_code=process.returncode if not timed_out else 124,
        stdout=out,
        stderr=err,
        duration_ms=(time.monotonic() - started) * 1000,
        timed_out=timed_out,
        command=COMMAND,
        summary_line=summary[:200],
    )
