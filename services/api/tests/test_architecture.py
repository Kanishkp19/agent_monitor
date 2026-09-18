"""The structural invariants, asserted rather than trusted.

`docs/DESIGN.md` section 3.1 states these as four greps. They are implemented
here as an AST walk instead, for one reason: grep matches strings in comments
and docstrings. This file's own prose mentions `boto3` a dozen times, and a
grep-based guard would either flag itself or need an exclusion that quietly
widens over time.

These are the invariants the AWS migration rests on. A red result here is not a
style nit -- it means domain code has learned which environment it is running
in, and the thirty-minute migration has become a rewrite.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "agentshield"

# Vendor SDKs, and the one package each is allowed to live in.
VENDOR_CONFINEMENT: dict[str, str] = {
    "boto3": "adapters/aws",
    "aioboto3": "adapters/aws",
    "botocore": "adapters/aws",
    "sqlite3": "adapters/local",
    "aiosqlite": "adapters/local",
    "httpx": "adapters/local",
}

# Only this module may import the adapter packages.
COMPOSITION_ROOT = "container.py"

# Only this module may read the environment variable.
CONFIG_MODULE = "config.py"
ENV_VAR = "AGENTSHIELD_ENV"


def _source_files() -> list[Path]:
    return sorted(p for p in PACKAGE_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _relative(path: Path) -> str:
    return path.relative_to(PACKAGE_ROOT).as_posix()


def _imported_modules(tree: ast.AST) -> set[str]:
    """Every module name referenced by an import, as its top-level package."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _parsed() -> list[tuple[Path, ast.Module]]:
    # `utf-8-sig` because an editor (or PowerShell's `Out-File`) may leave a
    # BOM, which `ast.parse` rejects. A guard that dies on a byte-order mark
    # reports a SyntaxError instead of the violation it was built to find.
    parsed: list[tuple[Path, ast.Module]] = []
    for path in _source_files():
        source = path.read_text(encoding="utf-8-sig")
        try:
            parsed.append((path, ast.parse(source, str(path))))
        except SyntaxError as exc:
            pytest.fail(f"cannot parse {_relative(path)}: {exc}")
    return parsed


# ──────────────────────────────────────────────────────────────────────
# I1 -- vendor SDKs stay inside their adapter package
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("vendor,allowed_dir", sorted(VENDOR_CONFINEMENT.items()))
def test_vendor_sdk_is_confined_to_its_adapter(vendor: str, allowed_dir: str) -> None:
    offenders: list[str] = []

    for path, tree in _parsed():
        rel = _relative(path)
        if rel.startswith(allowed_dir):
            continue
        for module in _imported_modules(tree):
            if module == vendor or module.startswith(f"{vendor}."):
                offenders.append(f"{rel} imports {module}")

    assert not offenders, (
        f"`{vendor}` may only be imported under `agentshield/{allowed_dir}/`. "
        f"Domain code needs a port instead.\n  " + "\n  ".join(offenders)
    )


# ──────────────────────────────────────────────────────────────────────
# I2 -- only the composition root knows adapters exist
# ──────────────────────────────────────────────────────────────────────


def test_only_container_imports_adapters() -> None:
    offenders: list[str] = []

    for path, tree in _parsed():
        rel = _relative(path)
        if rel == COMPOSITION_ROOT or rel.startswith("adapters/"):
            continue
        for module in _imported_modules(tree):
            if module.startswith("agentshield.adapters"):
                offenders.append(f"{rel} imports {module}")

    assert not offenders, (
        f"Only `agentshield/{COMPOSITION_ROOT}` may import from `adapters/`. "
        "Everything else depends on `agentshield.ports`.\n  " + "\n  ".join(offenders)
    )


def test_ports_package_has_no_adapter_dependency() -> None:
    """Ports are interfaces. An import here would invert the whole design."""
    offenders: list[str] = []

    for path, tree in _parsed():
        if not _relative(path).startswith("ports/"):
            continue
        for module in _imported_modules(tree):
            if module.startswith("agentshield.adapters"):
                offenders.append(f"{_relative(path)} imports {module}")

    assert not offenders, "ports/ must not import adapters/\n  " + "\n  ".join(offenders)


# ──────────────────────────────────────────────────────────────────────
# I3 -- exactly one file reads the environment, exactly one branches on it
# ──────────────────────────────────────────────────────────────────────


def test_only_config_reads_the_environment_variable() -> None:
    """`config.py` loads `AGENTSHIELD_ENV` into typed settings. Nothing else
    may reach for it -- see `docs/DECISIONS-RESOLVED.md` C6.
    """
    offenders: list[str] = []

    for path, tree in _parsed():
        rel = _relative(path)
        if rel == CONFIG_MODULE:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == ENV_VAR:
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        f"`{ENV_VAR}` may only appear in `agentshield/{CONFIG_MODULE}`.\n  "
        + "\n  ".join(offenders)
    )


def test_only_container_branches_on_the_environment() -> None:
    """The single `if settings.env == "aws"` in the codebase.

    This is the invariant that makes the migration a configuration change. A
    second branch anywhere means some behaviour differs between local and AWS
    that the contract tests are not covering.
    """
    offenders: list[str] = []

    for path, tree in _parsed():
        rel = _relative(path)
        if rel in (COMPOSITION_ROOT, CONFIG_MODULE):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and _reads_env_attribute(node.left):
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        f"Only `agentshield/{COMPOSITION_ROOT}` may branch on the environment.\n  "
        + "\n  ".join(offenders)
    )


def _reads_env_attribute(node: ast.expr) -> bool:
    """Match `settings.env`, `self.settings.env`, `container.settings.env`."""
    if not isinstance(node, ast.Attribute) or node.attr != "env":
        return False
    base = node.value
    if isinstance(base, ast.Name):
        return base.id == "settings"
    if isinstance(base, ast.Attribute):
        return base.attr == "settings"
    return False


# ──────────────────────────────────────────────────────────────────────
# I4 -- the detector has no path to the labels it is scored against
# ──────────────────────────────────────────────────────────────────────

LABEL_BEARING_MODULES = (
    "agentshield.sim.persona",
    "agentshield.sim.scenarios",
    "agentshield.sim.seed",
)


def test_risk_package_cannot_reach_the_ground_truth() -> None:
    """An evaluation you can fool is not an evaluation.

    `risk/` must not import the modules that know which employee is
    adversarial, and must not name `ScenarioProfile`. The runtime half of this
    guarantee is `RiskScopedDocStore`, which raises on any `GT#` read; this is
    the static half.
    """
    offenders: list[str] = []

    for path, tree in _parsed():
        rel = _relative(path)
        if not rel.startswith("risk/"):
            continue

        for module in _imported_modules(tree):
            if module in LABEL_BEARING_MODULES:
                offenders.append(f"{rel} imports {module}")

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "agentshield.domain.enums":
                for alias in node.names:
                    if alias.name == "ScenarioProfile":
                        offenders.append(f"{rel}:{node.lineno} imports ScenarioProfile")

    assert not offenders, "`risk/` must have no path to the ground-truth labels.\n  " + "\n  ".join(
        offenders
    )


# ──────────────────────────────────────────────────────────────────────
# Sanity: the guard is actually looking at something
# ──────────────────────────────────────────────────────────────────────


def test_guard_scans_a_plausible_number_of_files() -> None:
    """A guard that silently scans zero files passes forever.

    If the package is ever restructured and `PACKAGE_ROOT` stops resolving,
    every assertion above becomes vacuously true. This catches that.
    """
    files = _source_files()
    assert len(files) >= 20, f"only found {len(files)} source files under {PACKAGE_ROOT}"
    assert (PACKAGE_ROOT / COMPOSITION_ROOT).exists()
    assert (PACKAGE_ROOT / CONFIG_MODULE).exists()
