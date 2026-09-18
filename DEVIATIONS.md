# Deviations from the Specification

Every place the build differs from `docs/`, why, and what it cost. Contract
conflicts *between* the docs are a different thing and live in
`docs/DECISIONS-RESOLVED.md`.

Empty sections are good news. Keep it that way.

---

## Versions

**None.** Every pin in `docs/02-TRD.md` section 1 installed cleanly on Python
3.12: FastAPI 0.115.14, Pydantic 2.9.2, aiosqlite 0.20.0, boto3 1.35.36,
scikit-learn 1.5.2, numpy 2.1.3, pandas 2.2.3, pyarrow 17.0.0, moto 5.0.28,
ruff 0.7.4, mypy 1.13.0. The frozen set is `services/api/requirements.txt`.

---

## D-01 — Python 3.12, not 3.11

**Docs say:** Python 3.11.
**We use:** Python 3.12.2, via `py -3.12`.

The build machine has 3.10 on `PATH` and 3.12 installed; 3.11 is not present.
3.10 cannot run this project at all -- `domain/enums.py` uses `StrEnum`, which
is 3.11+. 3.12 satisfies the requirement and every pinned package has a 3.12
wheel.

`pyproject.toml` declares `requires-python = ">=3.11"`, so 3.11 remains
supported. `tasks.py setup` probes for 3.13, 3.12 then 3.11 and refuses to
build a venv on anything older, with a message naming `StrEnum` -- the failure
this prevents is otherwise a confusing `ImportError` forty files later.

---

## D-02 — `tasks.py` replaces the Makefile

**Docs say:** `make dev`, `make seed`, `make test-contract`, and so on.
**We use:** `python tasks.py <same-target-name>`.

Agreed with the project owner before Phase 0. The build machine is Windows and
has no `make`, no `sqlite3` CLI, no `jq` and no `websocat` -- four separate
dependencies for what is ultimately "run this command in that directory".

Target names are preserved one-for-one, so the command tables throughout
`docs/06-IMPLEMENTATION-PLAN.md` translate mechanically:

| Docs | Here |
|---|---|
| `make dev` | `python tasks.py dev` |
| `make advance DAYS=7` | `python tasks.py advance --days 7` |
| `sqlite3 .data/… "SELECT sk FROM items…"` | `python tasks.py inspect-events` |
| `grep -r "AKIA…" .data/agentshield.db` | `python tasks.py check-secrets` |
| `websocat "ws://…/ws/stream"` | `python infra/scripts/ws_tail.py` |
| `curl … \| jq` | plain `curl`, or `Invoke-RestMethod` |

`tasks.py` is standard library only, so it needs no bootstrap install.

---

## D-03 — The architecture guard is an AST walk, not four greps

**Docs say:** `docs/DESIGN.md` section 3.1 specifies four `grep` pipelines,
asserted in `tests/test_architecture.py`.
**We use:** the same four rules, implemented by parsing each module and
inspecting its import nodes.

Grep matches strings in comments and docstrings. `tests/test_architecture.py`
names `boto3` a dozen times while explaining why `boto3` is banned; a
grep-based guard would flag itself, and the exclusion needed to silence that
would quietly widen over time until the guard stopped guarding.

The AST version is also more precise: it distinguishes `if settings.env ==
"aws"` (a branch, allowed only in `container.py`) from the string
`AGENTSHIELD_ENV` (a read, allowed only in `config.py`), which is the
distinction `docs/DECISIONS-RESOLVED.md` C6 turns on and which grep cannot make.

The guard has been verified to fail: a probe module importing `boto3`, reading
the environment variable and branching on it produced four precise
`file:line` detections, and removing it returned the suite to green.

---

## D-04 — AWS adapters call boto3 synchronously on a worker thread

**Docs say:** `aioboto3` for "async paths in AWS adapters only"
(`docs/02-TRD.md` section 1).
**We use:** `boto3` wrapped in `asyncio.to_thread`. `aioboto3` stays in
`requirements.txt` and is available if a future workload needs it.

Two reasons, both about trust in the contract suite:

1. `moto` instruments botocore's synchronous stack. Against `aiobotocore` its
   coverage is partial and version-sensitive. The contract tests are the entire
   evidence that the AWS adapters work without an AWS account, so they have to
   be believable.
2. DynamoDB and S3 calls are single-digit milliseconds. A thread hop costs less
   than the dependency risk, and the port surface is `async` either way, so
   nothing upstream can tell the difference.

The one place this would matter is a high-fan-out workload saturating the
default thread pool. The simulation runs at most four concurrent agent
sessions (`SIM_MAX_CONCURRENT_SESSIONS`), so it does not arise.

---

## D-05 — Third-party deprecation warnings are exempted individually

`pyproject.toml` sets `filterwarnings = ["error::DeprecationWarning"]`, so our
own deprecations fail the build. Two pinned libraries emit warnings we cannot
fix:

| Library | Warning | Why it is theirs, not ours |
|---|---|---|
| boto3 / botocore 1.35 | `datetime.utcnow()` is deprecated | raised inside `botocore.auth` on every signed request |
| starlette 0.46 | `anyio.abc.BlockingPortal` alias is deprecated | raised at import time by `starlette.testclient` |

Each is exempted by name and message, never by a blanket ignore, so the next
library to start emitting warnings still fails loudly.

---

## D-06 — `pip install -e .` for the API package

`services/api/pyproject.toml` exists in the folder tree in
`docs/00-MASTER-PROMPT.md`, but no doc says to install the package. Installing
it editable means `import agentshield` resolves the same way from the repo
root, from `services/api/`, and from pytest, rather than depending on which
directory a command happened to start in. `tasks.py setup` does it.

The file also carries the ruff, mypy and pytest configuration, which otherwise
needs three more config files.

---

## D-07 — Four frontend pins bumped; the docs' own pin table is inconsistent

`docs/02-TRD.md` section 1 pins React 19.0 alongside three packages whose
published peer ranges stop at React 18. Those pins cannot coexist -- `npm
install` refuses the tree. Each was raised by the smallest amount that admits
React 19, staying inside the pinned major every time:

| Package | Docs | Here | Why |
|---|---|---|---|
| `@tanstack/react-virtual` | 3.10.x | ~3.11.0 | React 19 peer added in 3.11.0 |
| `recharts` | 2.13.x | ~2.15.0 | React 19 peer added in 2.15; still the 2.x line |
| `@testing-library/react` | 16.0.x | ~16.1.0 | React 19 peer added in 16.1.0 |
| `vite` | 6.0.x | ^6.4.3 | see D-08; still Vite 6 |

No API used by this project changed across any of those bumps.

---

## D-08 — Vite raised to 6.4.3 for a published advisory

Vite `<= 6.4.2` carries a high-severity dev-server advisory, and `~6.0.0`
would have resolved to 6.0.15. `^6.4.3` is the first patched release and stays
within the pinned major.

**What ships is clean:** `npm audit --omit=dev` reports zero vulnerabilities.

Five findings remain under `npm audit` with dev dependencies included, all
tracing to one root: `vitest@2.1` (the pinned version) bundles its own
`vite@5.4.21` and `esbuild@0.24.2` for the test runner. Clearing them requires
vitest 5, which requires Vite 7 -- outside the pinned major, for a toolchain
that never serves a request or emits a byte into the bundle.

Revisit if vitest ships a 2.x patch, or when the Vite pin is next reviewed.
