#!/usr/bin/env python
"""AgentShield task runner.

Replaces the Makefile from the docs with something that runs identically on
Windows, macOS and Linux. Standard library only -- no install step, no
`make`, no `jq`, no `sqlite3` CLI.

    python tasks.py <target> [options]
    python tasks.py --list

Every target name matches the `make` target it replaces, so the commands in
`docs/06-IMPLEMENTATION-PLAN.md` translate one-for-one:

    make dev            ->  python tasks.py dev
    make test-contract  ->  python tasks.py test-contract
    make advance DAYS=7 ->  python tasks.py advance --days 7
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

ROOT = Path(__file__).resolve().parent
API = ROOT / "services" / "api"
WEB = ROOT / "apps" / "web"
VENV = API / ".venv"
IS_WINDOWS = platform.system() == "Windows"

# The interpreter this project runs on. `python` on PATH may be too old --
# domain/enums.py uses StrEnum, which is 3.11+.
MIN_PYTHON = (3, 11)


# ──────────────────────────────────────────────────────────────────────
# Process helpers
# ──────────────────────────────────────────────────────────────────────

def venv_python() -> Path:
    return VENV / ("Scripts" if IS_WINDOWS else "bin") / ("python.exe" if IS_WINDOWS else "python")


def require_venv() -> Path:
    py = venv_python()
    if not py.exists():
        die(f"No virtualenv at {VENV}.\n  Run: python tasks.py setup")
    return py


def die(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def run(cmd: Sequence[str | Path], *, cwd: Path = ROOT, check: bool = True,
        env: dict[str, str] | None = None) -> int:
    """Run a command, streaming its output. Returns the exit code."""
    printable = " ".join(str(c) for c in cmd)
    print(f"\n$ {printable}\n", flush=True)
    merged = {**os.environ, **(env or {})}
    result = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=merged)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.returncode


def npm() -> str:
    """npm is a .cmd shim on Windows and must be resolved before exec."""
    found = shutil.which("npm")
    if not found:
        die("npm not found on PATH. Install Node 20+.")
    return found


# ──────────────────────────────────────────────────────────────────────
# Targets
# ──────────────────────────────────────────────────────────────────────

def target_setup(args: argparse.Namespace) -> None:
    """Create the venv, install both dependency sets, seed .env files."""
    if not VENV.exists():
        interpreter = _find_modern_python()
        print(f"Creating virtualenv with {interpreter}")
        run([interpreter, "-m", "venv", str(VENV)])

    py = venv_python()
    run([py, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
    req = API / "requirements.txt"
    if req.exists():
        run([py, "-m", "pip", "install", "-r", str(req)])
    else:
        print(f"note: {req} not present yet -- skipping backend install")

    if (WEB / "package.json").exists():
        run([npm(), "install"], cwd=WEB)
    else:
        print(f"note: {WEB / 'package.json'} not present yet -- skipping web install")

    _copy_if_missing(ROOT / ".env.example", ROOT / ".env")
    _copy_if_missing(WEB / ".env.example", WEB / ".env")
    print("\nsetup complete. Next: python tasks.py seed")


def _find_modern_python() -> str:
    """Locate a >=3.11 interpreter. `python` on PATH is often too old."""
    if sys.version_info >= MIN_PYTHON:
        return sys.executable
    if IS_WINDOWS and shutil.which("py"):
        for minor in ("3.13", "3.12", "3.11"):
            resolved = _py_launcher_path(minor)
            if resolved:
                return resolved
    for name in ("python3.13", "python3.12", "python3.11"):
        found = shutil.which(name)
        if found:
            return found
    die(
        f"Need Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ (StrEnum). "
        f"Running under {platform.python_version()}."
    )
    raise AssertionError("unreachable")


def _py_launcher_path(minor: str) -> str:
    """Resolve `py -3.x` to a concrete executable path, or "" if absent."""
    probe = subprocess.run(
        ["py", f"-{minor}", "-c", "import sys; print(sys.executable)"],
        capture_output=True, text=True,
    )
    return probe.stdout.strip() if probe.returncode == 0 else ""


def _copy_if_missing(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        shutil.copyfile(src, dst)
        print(f"created {dst.relative_to(ROOT)} from {src.name}")


def target_api(args: argparse.Namespace) -> None:
    """Run the FastAPI server alone."""
    py = require_venv()
    run([py, "-m", "uvicorn", "agentshield.main:app", "--reload",
         "--host", os.environ.get("API_HOST", "0.0.0.0"),
         "--port", os.environ.get("API_PORT", "8000")], cwd=API)


def target_web(args: argparse.Namespace) -> None:
    """Run the Vite dev server alone."""
    run([npm(), "run", "dev"], cwd=WEB)


def target_dev(args: argparse.Namespace) -> None:
    """Run API on :8000 and web on :5173 together."""
    py = require_venv()
    procs: list[subprocess.Popen[bytes]] = []
    try:
        procs.append(subprocess.Popen(
            [str(py), "-m", "uvicorn", "agentshield.main:app", "--reload",
             "--host", "0.0.0.0", "--port", "8000"], cwd=str(API)))
        if (WEB / "package.json").exists():
            procs.append(subprocess.Popen([npm(), "run", "dev"], cwd=str(WEB)))
        print("\napi  -> http://localhost:8000")
        print("web  -> http://localhost:5173")
        print("\nCtrl-C to stop both.\n")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


def target_test(args: argparse.Namespace) -> None:
    """Run the full backend suite."""
    py = require_venv()
    run([py, "-m", "pytest", "-v"], cwd=API)


def target_test_contract(args: argparse.Namespace) -> None:
    """Run the port contract suites against BOTH adapter sets.

    A skipped `aws` parameter is the AWS migration failing eight days early,
    so this target fails on skips rather than reporting green.
    """
    py = require_venv()
    run([py, "-m", "pytest", "tests/contract", "-v", "-ra",
         "-W", "error::pytest.PytestUnraisableExceptionWarning"], cwd=API)


def target_typecheck(args: argparse.Namespace) -> None:
    """mypy --strict on the layers that must not drift."""
    py = require_venv()
    run([py, "-m", "mypy", "agentshield/domain", "agentshield/ports",
         "agentshield/governance", "agentshield/risk"], cwd=API)


def target_lint(args: argparse.Namespace) -> None:
    """ruff check + format verification."""
    py = require_venv()
    run([py, "-m", "ruff", "check", "agentshield", "tests"], cwd=API)
    run([py, "-m", "ruff", "format", "--check", "agentshield", "tests"], cwd=API)


def target_fmt(args: argparse.Namespace) -> None:
    """Apply ruff formatting."""
    py = require_venv()
    run([py, "-m", "ruff", "check", "--fix", "agentshield", "tests"], cwd=API, check=False)
    run([py, "-m", "ruff", "format", "agentshield", "tests"], cwd=API)


def target_contracts(args: argparse.Namespace) -> None:
    """Regenerate Pydantic + TypeScript types from events.schema.json."""
    py = require_venv()
    run([py, str(ROOT / "packages" / "contracts" / "generate.py")], cwd=ROOT)


def target_seed(args: argparse.Namespace) -> None:
    """Seed a run: 20 employees, 6 repos with file trees, 12 policies."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.seed_run"], cwd=API)


def target_seed_policies(args: argparse.Namespace) -> None:
    """Seed only the 12 policies (Phase 2 -- before employees exist)."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.seed_run", "--policies-only"], cwd=API)


def target_seed_history(args: argparse.Namespace) -> None:
    """Advance 14 sim-days so risk baselines exist.

    Without this every employee stays `low_confidence` and the risk engine
    has nothing to compare against.
    """
    py = require_venv()
    run([py, "-m", "agentshield.scripts.advance", "--days", "14"], cwd=API)


def target_advance(args: argparse.Namespace) -> None:
    """Fast-forward the simulation headlessly."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.advance", "--days", str(args.days)], cwd=API)


def target_inspect_events(args: argparse.Namespace) -> None:
    """Print stored event keys for a run (replaces the `sqlite3` CLI check)."""
    py = require_venv()
    cmd = [py, "-m", "agentshield.scripts.inspect_events", "--limit", str(args.limit)]
    if args.run_id:
        cmd += ["--run-id", args.run_id]
    run(cmd, cwd=API)


def target_check_secrets(args: argparse.Namespace) -> None:
    """Assert no raw secret literal was ever persisted. Must stay at zero."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.check_secrets"], cwd=API)


def target_repro_check(args: argparse.Namespace) -> None:
    """Run the same seed twice and assert identical event-stream hashes."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.repro_check"], cwd=API)


def target_run_task(args: argparse.Namespace) -> None:
    """Drive one agent task end to end through both gates."""
    py = require_venv()
    cmd = [py, "-m", "agentshield.scripts.run_task",
           "--employee", args.employee, "--task", args.task]
    if args.repo:
        cmd += ["--repo", args.repo]
    if args.env:
        cmd += ["--env", args.env]
    run(cmd, cwd=API)


def target_gate_repl(args: argparse.Namespace) -> None:
    """Interactive gate console for probing policy decisions by hand."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.gate_repl"], cwd=API)


def target_train_risk(args: argparse.Namespace) -> None:
    """Train the IsolationForest on the trailing session window."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.train_risk"], cwd=API)


def target_evaluate(args: argparse.Namespace) -> None:
    """Score the detector against ground truth. Post-hoc, offline, never in-band."""
    py = require_venv()
    run([py, str(ROOT / "infra" / "scripts" / "evaluate.py")], cwd=API)


def target_export_dataset(args: argparse.Namespace) -> None:
    """Write sessions/events/labels parquet plus a DATASET-CARD.md."""
    py = require_venv()
    run([py, str(ROOT / "infra" / "scripts" / "export_dataset.py")], cwd=API)


def target_demo(args: argparse.Namespace) -> None:
    """Run the scripted three-minute scenario, unattended."""
    py = require_venv()
    run([py, "-m", "agentshield.scripts.demo"], cwd=API)


def target_build(args: argparse.Namespace) -> None:
    """Production build of the web app. Must be zero TS errors."""
    run([npm(), "run", "build"], cwd=WEB)


def target_atlas(args: argparse.Namespace) -> None:
    """Generate the placeholder office art.

    Flat-coloured tiles and blocky characters, so the scene is never blocked
    on an art decision. Real art drops in by replacing two PNGs and their
    JSON, with zero code change.
    """
    py = require_venv()
    run([py, str(ROOT / "infra" / "scripts" / "make_placeholder_atlas.py")], cwd=ROOT)


def target_clean(args: argparse.Namespace) -> None:
    """Delete generated runtime data. Does not touch source."""
    for path in (ROOT / ".data", API / ".pytest_cache", API / ".mypy_cache",
                 API / ".ruff_cache", WEB / "dist"):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            print(f"removed {path.relative_to(ROOT)}")


def target_test_web(args: argparse.Namespace) -> None:
    """Run the web test suite (vitest)."""
    run([npm(), "run", "test"], cwd=WEB)


def target_lint_web(args: argparse.Namespace) -> None:
    """Lint the web app (eslint)."""
    run([npm(), "run", "lint"], cwd=WEB)


def target_check(args: argparse.Namespace) -> None:
    """Everything the CI gate runs: lint, types, tests, build -- both sides.

    Run this before every commit. The contract suite and the architecture
    guard are the project's structural integrity; a red commit there compounds.
    """
    steps: list[tuple[str, Target]] = [
        ("lint (api)", target_lint),
        ("typecheck (api)", target_typecheck),
        ("test (api)", target_test),
        ("lint (web)", target_lint_web),
        ("test (web)", target_test_web),
        ("build (web)", target_build),
    ]
    rule = "=" * 62
    for name, step in steps:
        print(f"\n{rule}\n  {name}\n{rule}")
        step(args)
    print("\nall checks passed")


# ──────────────────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────────────────

Target = Callable[[argparse.Namespace], None]

TARGETS: dict[str, Target] = {
    "setup": target_setup,
    "dev": target_dev,
    "api": target_api,
    "web": target_web,
    "build": target_build,
    "check": target_check,
    "test": target_test,
    "test-contract": target_test_contract,
    "test-web": target_test_web,
    "typecheck": target_typecheck,
    "lint": target_lint,
    "lint-web": target_lint_web,
    "fmt": target_fmt,
    "contracts": target_contracts,
    "seed": target_seed,
    "seed-policies": target_seed_policies,
    "seed-history": target_seed_history,
    "advance": target_advance,
    "inspect-events": target_inspect_events,
    "check-secrets": target_check_secrets,
    "repro-check": target_repro_check,
    "run-task": target_run_task,
    "gate-repl": target_gate_repl,
    "train-risk": target_train_risk,
    "evaluate": target_evaluate,
    "export-dataset": target_export_dataset,
    "demo": target_demo,
    "atlas": target_atlas,
    "clean": target_clean,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tasks.py",
        description="AgentShield task runner (cross-platform Makefile replacement).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", action="store_true", help="list every target and exit")
    sub = parser.add_subparsers(dest="target")

    for name, fn in TARGETS.items():
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        p = sub.add_parser(name, help=doc, description=fn.__doc__)
        if name == "advance":
            p.add_argument("--days", type=int, default=1, help="sim-days to advance (1-30)")
        if name == "inspect-events":
            p.add_argument("--run-id", help="run to inspect (default: most recent)")
            p.add_argument("--limit", type=int, default=10, help="rows to print")
        if name == "run-task":
            p.add_argument("--employee", required=True, help="e.g. emp_013")
            p.add_argument("--task", required=True, help="task title")
            p.add_argument("--repo", help="e.g. payments-api")
            p.add_argument("--env", choices=["local", "staging", "production"])
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list or not args.target:
        width = max(len(n) for n in TARGETS)
        print("AgentShield targets:\n")
        for name, fn in TARGETS.items():
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            print(f"  {name.ljust(width)}  {doc}")
        print("\n  python tasks.py <target> --help   for per-target options")
        return 0

    TARGETS[args.target](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
