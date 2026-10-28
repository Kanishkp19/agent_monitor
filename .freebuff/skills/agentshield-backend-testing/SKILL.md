---
name: agentshield-backend-testing
description: Use when writing or running tests for services/api, or before declaring backend work done. Covers pytest setup on macOS (rebuild venv from Linux/Windows venvs), the contract suites, the architecture guard, and the exact verification commands per change type.
alwaysApply: false
globs:
  - "services/api/tests/**/*.py"
  - "services/api/pytest.ini"
  - "services/api/pyproject.toml"
---

# Backend testing & verification (services/api)

## Environment reality check (do this first on a fresh checkout)

The backend venv lives at `services/api/.venv` but is **not portable across OSes** — a
venv created on Windows (`Scripts/`) or Linux (`bin/` + Linux python ABI) is dead weight
on macOS. If `services/api/.venv/bin/python` does not exist, rebuild:

```bash
cd Agent-Shield-
/opt/homebrew/bin/python3.12 -m venv services/api/.venv     # 3.11+ required (StrEnum)
services/api/.venv/bin/python -m pip install --upgrade pip
services/api/.venv/bin/python -m pip install -r services/api/requirements.txt
services/api/.venv/bin/python -m pip install -e services/api  # editable install = `import agentshield` works anywhere
cp .env.example .env 2>/dev/null || true
```

System `python` may be 3.9 — always use the venv interpreter explicitly. `tasks.py`
targets (`test`, `lint`, `typecheck`, `check`, …) all go through this venv.

## The suites and what each protects

| Suite | Protects |
|---|---|
| `tests/test_architecture.py` | The AST guard: vendor SDKs only in `adapters/`, only `container.py` branches on env, only `config.py` reads `AGENTSHIELD_ENV`, `risk/` can't reach `GT#`/ground truth. Sanity check scans ≥ 20 files. **The** structural-integrity gate — run it after ANY backend change. |
| `tests/contract/` | Same suite run against BOTH adapter sets (local + `moto` for AWS). Parameterised; **skips fail the run** (`-W error::pytest.PytestUnraisableExceptionWarning`). Touching `ports/` or either `adapters/` set ⇒ run `test-contract`, not just `test`. |
| `tests/unit/`, `tests/e2e/` | Gate behaviour, domain models, health. |
| `pytest-benchmark` | Perf regressions on hot paths. |

pyproject test config: `asyncio_mode = auto`, `filterwarnings` turns `DeprecationWarning`
into errors **with named third-party exemptions only** (boto3 `utcnow`, starlette
BlockingPortal). If your code emits a DeprecationWarning, the suite fails — fix the call,
don't widen the filter.

## What to run for each change type

| Changed | Run |
|---|---|
| Anything in `services/api/agentshield/` | `python tasks.py test` + `python tasks.py lint` |
| `governance/`, `risk/`, `domain/`, `ports/` | + `python tasks.py typecheck` (mypy strict on those layers) |
| `ports/` or `adapters/**` | + `python tasks.py test-contract` (skips fail) |
| `sim/`, `agent/`, `sandbox/`, `telemetry/` | + `python tasks.py repro-check` (same seed ⇒ identical event hash) |
| Any event emission / policy decision / secret handling | + `python tasks.py check-secrets` (canary scan MUST be zero) |
| `packages/contracts/events.schema.json` | `python tasks.py contracts`, commit both generated files together |
| Pre-finish (everything) | `python tasks.py check` — lint+mypy+tests+web build, both sides |

## Conventions for new tests

- Place per layer: port behaviour → `tests/contract/` (write once, runs against both
  adapter sets); governance/risk logic → `tests/unit/`; route behaviour → e2e via the
  FastAPI test client.
- Async tests just work (`asyncio_mode = auto`) — no decorators needed.
- Seeds and determinism: never `random.random()` in tests that assert on sim output; use
  seeded draws. Assertions on ordering must use `seq`, never timestamps.
- Do not mock the DocStore port with a dict — use the real `SqliteDocStore` (tmp path) so
  key-layout assumptions stay exercised.
- mypy strict applies to `domain/`, `ports/`, `governance/`, `risk/` — annotate everything,
  no untyped dicts crossing module boundaries (` Any` soup fails the gate).
