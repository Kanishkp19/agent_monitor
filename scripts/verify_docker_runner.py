#!/usr/bin/env python3
"""Offline verification using the production runner; never invokes a model.

Run with services/api/.venv/bin/python scripts/verify_docker_runner.py.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))

from agentshield.autopilot.test_runner import (  # noqa: E402
    IMAGE,
    IsolationUnavailable,
    require_isolation,
    run_tests,
)
from agentshield.autopilot.workspace import WorkspaceManager  # noqa: E402

ISOLATION_TEST = """
import os
import socket
from pathlib import Path
import pytest

def test_isolation():
    assert os.getuid() == 65534
    assert not Path('/var/run/docker.sock').exists()
    interfaces = Path('/proc/net/dev').read_text().splitlines()[2:]
    # Some Docker kernels expose down tunnel devices even with --network none.
    names = {line.split(':')[0].strip() for line in interfaces}
    assert {
        name for name in names
        if int((Path('/sys/class/net') / name / 'flags').read_text(), 16) & 1
    } == {'lo'}
    with socket.socket() as connection:
        connection.settimeout(1)
        assert connection.connect_ex(('1.1.1.1', 443)) != 0
    with pytest.raises(OSError):
        Path('/workspace/forbidden').write_text('write')
    assert Path('/sys/fs/cgroup/memory.max').read_text().strip() == '268435456'
    quota, period = map(int, Path('/sys/fs/cgroup/cpu.max').read_text().split())
    assert quota == period
    assert Path('/sys/fs/cgroup/pids.max').read_text().strip() == '64'
"""


def docker_command(
    *args: str, check: bool = True, timeout: int = 10
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("docker")
    if executable is None:
        raise IsolationUnavailable("Docker CLI is missing. Install and start Docker, then rerun.")
    return subprocess.run(  # noqa: S603 - resolved Docker executable and fixed local arguments
        [executable, *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


async def verify() -> None:
    await asyncio.to_thread(docker_command, "info")
    image = await asyncio.to_thread(docker_command, "image", "inspect", IMAGE, check=False)
    if image.returncode:
        await asyncio.to_thread(
            docker_command,
            "build",
            "-t",
            IMAGE,
            str(ROOT / "infra/autopilot"),
            timeout=300,
        )
    await asyncio.to_thread(require_isolation)
    before = await asyncio.to_thread(
        docker_command, "ps", "-aq", "--filter", "name=agentshield-test-"
    )
    with tempfile.TemporaryDirectory(prefix="agentshield-runner-") as directory:
        manager = WorkspaceManager(
            fixtures_dir=ROOT / "infra/fixtures",
            workspaces_dir=Path(directory).resolve(),
        )
        workspace = manager.create("buggy-auth")
        try:
            baseline = await run_tests(workspace)
            assert baseline.exit_code == 1 and not baseline.timed_out, baseline.preview()
            print("PASS: real buggy-auth baseline captures pytest exit 1")
            # Only the disposable copy changes. Run the same fixed pytest command.
            for test in (workspace.root / "tests").glob("test_*.py"):
                test.unlink()
            probe = workspace.root / "tests/test_isolation.py"
            probe.write_text(ISOLATION_TEST, encoding="utf-8")
            isolated = await run_tests(workspace)
            assert isolated.passed and isolated.exit_code == 0, isolated.preview()
            print("PASS: UID, network, read-only mount, no socket, CPU/memory/PID limits")
            probe.write_text("import time\ndef test_timeout(): time.sleep(30)\n", encoding="utf-8")
            workspace.manifest = workspace.manifest.model_copy(update={"timeout_seconds": 5})
            timeout = await run_tests(workspace)
            assert timeout.timed_out and timeout.exit_code == 124 and not timeout.passed
            assert timeout.duration_ms < 20_000, timeout.preview()
            containers = await asyncio.to_thread(
                docker_command,
                "ps",
                "-aq",
                "--filter",
                "name=agentshield-test-",
            )
            assert set(containers.stdout.split()) <= set(
                before.stdout.split()
            ), "runner container remained after timeout"
            print("PASS: timeout captures exit 124 and removes container")
        finally:
            manager.cleanup(workspace)


def main() -> int:
    try:
        asyncio.run(verify())
    except (IsolationUnavailable, subprocess.SubprocessError, OSError, AssertionError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("Docker runner offline verification passed; no Nebius calls made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
