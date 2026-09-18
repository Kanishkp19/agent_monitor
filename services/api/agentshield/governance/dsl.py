"""The policy condition language.

A deliberately small JSON DSL: eleven operators, three combinators, a fixed
field allowlist per gate. Small enough that a decision trace is readable by a
human at 2 a.m., which is the only audience that matters.

Two design choices worth stating:

**An unknown field is an error, not a no-match.** A policy that silently never
fires is worse than one that refuses to save -- the operator believes they are
protected and they are not. Every validation failure carries the exact JSON
path, so the editor can point at it.

**`source` is absent from both allowlists.** A policy that could read whether
a request came from the simulator or a real agent could behave differently in
the two modes, and mode parity would become a claim instead of a property.
"""

from __future__ import annotations

import re
from typing import Any, cast

from agentshield.domain.enums import Gate
from agentshield.domain.errors import PolicyInvalid

FIELDS_GATE1: frozenset[str] = frozenset(
    {
        "actor.role",
        "actor.team",
        "actor.seniority",
        "actor.prod_access",
        "actor.risk_score",
        "actor.spend_today_usd",
        "actor.daily_budget_usd",
        "actor.sessions_today",
        "actor.is_low_confidence",
        "request.task_type",
        "request.complexity",
        "request.repo",
        "request.environment",
        "request.prompt_len",
        "request.requested_model",
        "request.est_cost_usd",
        "request.est_input_tokens",
        "request.routed_model",
        "request.findings_count",
        "request.finding_types",
        "request.off_hours",
    }
)

FIELDS_GATE2: frozenset[str] = frozenset(
    {
        "actor.role",
        "actor.team",
        "actor.seniority",
        "actor.prod_access",
        "actor.risk_score",
        "actor.is_low_confidence",
        "action.tool",
        "action.environment",
        "action.target_resource",
        "action.resource_sensitivity",
        "action.repeat_count_5m",
        "action.iteration_index",
        "task.repo",
        "task.is_repo_in_scope",
        "task.is_secret_path",
        "task.is_protected_branch",
        "task.is_external_host",
        "task.cost_so_far_usd",
        "task.blocked_so_far",
        "task.elapsed_sim_s",
    }
)

OPS: frozenset[str] = frozenset(
    {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "matches", "contains", "exists"}
)
COMBINATORS: frozenset[str] = frozenset({"all", "any", "none"})

LIST_OPS: frozenset[str] = frozenset({"in", "not_in"})
NUMERIC_OPS: frozenset[str] = frozenset({"gt", "gte", "lt", "lte"})

MAX_DEPTH = 5
MAX_CONDITIONS = 25

# A regex from an operator-authored policy runs on every evaluation. Capping
# the pattern length is a cheap guard against a catastrophic backtracker
# reaching the hot path.
MAX_PATTERN_LENGTH = 200


def fields_for(gate: Gate | int) -> frozenset[str]:
    return FIELDS_GATE1 if int(gate) == 1 else FIELDS_GATE2


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def validate(node: Any, gate: Gate | int) -> list[tuple[str, str]]:
    """Walk a condition tree. Returns `[(json_path, message)]`, empty if valid.

    Never raises -- the caller decides whether a problem is a 400 or a warning.
    `PolicyCreate` turns the first entry into a `PolicyInvalid` carrying the
    path, which is what the editor underlines.
    """
    errors: list[tuple[str, str]] = []
    counted = _Counter()
    _walk(node, gate, "when", 1, errors, counted)
    if counted.value > MAX_CONDITIONS:
        errors.append(("when", f"too many conditions ({counted.value} > {MAX_CONDITIONS})"))
    return errors


class _Counter:
    __slots__ = ("value",)

    def __init__(self) -> None:
        self.value = 0


def _walk(
    node: Any,
    gate: Gate | int,
    path: str,
    depth: int,
    errors: list[tuple[str, str]],
    counted: _Counter,
) -> None:
    if depth > MAX_DEPTH:
        errors.append((path, f"condition nested deeper than {MAX_DEPTH}"))
        return

    if not isinstance(node, dict):
        errors.append((path, "condition must be an object"))
        return

    combinator = next((c for c in COMBINATORS if c in node), None)
    if combinator is not None:
        branches = node[combinator]
        if not isinstance(branches, list) or not branches:
            errors.append((f"{path}.{combinator}", f"'{combinator}' must be a non-empty array"))
            return
        unknown = set(node) - COMBINATORS
        if unknown:
            errors.append((path, f"unexpected keys alongside '{combinator}': {sorted(unknown)}"))
        for index, branch in enumerate(branches):
            _walk(branch, gate, f"{path}.{combinator}[{index}]", depth + 1, errors, counted)
        return

    _validate_leaf(node, gate, path, errors, counted)


def _validate_leaf(
    node: dict[str, Any],
    gate: Gate | int,
    path: str,
    errors: list[tuple[str, str]],
    counted: _Counter,
) -> None:
    counted.value += 1
    allowed = fields_for(gate)

    field = node.get("field")
    if not isinstance(field, str):
        errors.append((f"{path}.field", "missing 'field'"))
        return
    if field not in allowed:
        errors.append((f"{path}.field", _unknown_field_message(field, allowed)))

    op = node.get("op")
    if not isinstance(op, str):
        errors.append((f"{path}.op", "missing 'op'"))
        return
    if op not in OPS:
        errors.append((f"{path}.op", f'unknown operator "{op}". Allowed: {sorted(OPS)}'))
        return

    if op == "exists":
        return

    if "value" not in node:
        errors.append((f"{path}.value", f"operator '{op}' requires a value"))
        return

    value = node["value"]
    if op in LIST_OPS and not isinstance(value, list):
        errors.append((f"{path}.value", f"operator '{op}' requires an array"))
    if op in NUMERIC_OPS and (isinstance(value, bool) or not isinstance(value, int | float)):
        errors.append((f"{path}.value", f"operator '{op}' requires a number"))
    if op == "matches":
        if not isinstance(value, str):
            errors.append((f"{path}.value", "operator 'matches' requires a string pattern"))
        elif len(value) > MAX_PATTERN_LENGTH:
            errors.append((f"{path}.value", f"pattern longer than {MAX_PATTERN_LENGTH} characters"))
        else:
            try:
                re.compile(value)
            except re.error as exc:
                errors.append((f"{path}.value", f"invalid regular expression: {exc}"))


def _unknown_field_message(field: str, allowed: frozenset[str]) -> str:
    """Name the mistake and, where possible, the fix.

    `docs/04-UI-UX-BRIEF.md` section 9 asks for exactly this shape:
    "Unknown field "actor.department" at when.all[1].field. Did you mean
    "actor.team"?" -- not "Invalid input".
    """
    suggestion = _closest(field, allowed)
    message = f'unknown field "{field}"'
    if suggestion:
        message += f'. Did you mean "{suggestion}"?'
    return message


def _closest(needle: str, haystack: frozenset[str]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(needle, sorted(haystack), n=1, cutoff=0.6)
    return matches[0] if matches else None


def validate_or_raise(node: Any, gate: Gate | int) -> None:
    errors = validate(node, gate)
    if errors:
        path, message = errors[0]
        raise PolicyInvalid(message, field=path, details={"errors": errors})


def fields_used(node: Any) -> list[str]:
    """Every field a condition reads. Surfaced by `POST /policies/validate`."""
    found: set[str] = set()
    _collect_fields(node, found)
    return sorted(found)


def _collect_fields(node: Any, into: set[str]) -> None:
    if not isinstance(node, dict):
        return
    combinator = next((c for c in COMBINATORS if c in node), None)
    if combinator is not None:
        for branch in node[combinator]:
            _collect_fields(branch, into)
        return
    field = node.get("field")
    if isinstance(field, str):
        into.add(field)


# ──────────────────────────────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────────────────────────────


def evaluate(node: Any, context: dict[str, Any]) -> bool:
    """Evaluate a validated condition against a flat context map.

    `context` comes from `RequestContext.policy_view()` or
    `ActionContext.policy_view()`. Neither includes `source`.

    An empty condition matches everything -- that is how an unconditional
    policy is written, and it is deliberate rather than an oversight.
    """
    if not node:
        return True
    if not isinstance(node, dict):
        return False

    if "all" in node:
        return all(evaluate(b, context) for b in node["all"])
    if "any" in node:
        return any(evaluate(b, context) for b in node["any"])
    if "none" in node:
        return not any(evaluate(b, context) for b in node["none"])

    return _evaluate_leaf(node, context)


def _evaluate_leaf(node: dict[str, Any], context: dict[str, Any]) -> bool:
    field = node.get("field")
    op = node.get("op")
    if not isinstance(field, str) or not isinstance(op, str):
        return False

    present = field in context
    actual = context.get(field)

    if op == "exists":
        want = node.get("value", True)
        return (present and actual is not None) is bool(want)

    # A field that is absent or null cannot satisfy a comparison. Returning
    # False rather than raising means one stale field in a policy degrades
    # that policy, not the whole evaluation.
    if not present or actual is None:
        return False

    # `dict[str, Any].get()` types as `Any | None`; the cast to `Any` is what
    # actually erases the `| None`, since policies with a required value were
    # already rejected by `validate()` before they could reach here.
    expected: Any = cast(Any, node.get("value"))

    try:
        if op == "eq":
            return bool(_coerce(actual) == _coerce(expected))
        if op == "neq":
            return bool(_coerce(actual) != _coerce(expected))
        if op == "in":
            return _coerce(actual) in {_coerce(v) for v in expected}
        if op == "not_in":
            return _coerce(actual) not in {_coerce(v) for v in expected}
        if op == "gt":
            return float(actual) > float(expected)
        if op == "gte":
            return float(actual) >= float(expected)
        if op == "lt":
            return float(actual) < float(expected)
        if op == "lte":
            return float(actual) <= float(expected)
        if op == "matches":
            return re.search(str(expected), str(actual)) is not None
        if op == "contains":
            if isinstance(actual, list | tuple | set):
                return _coerce(expected) in {_coerce(v) for v in actual}
            return str(expected) in str(actual)
    except (TypeError, ValueError, re.error):
        return False

    return False


def _coerce(value: Any) -> Any:
    """Compare enums and strings by value.

    `Role.INTERN` and `"engineering_intern"` are the same thing to a policy
    author, and a policy written against the string must match a context
    carrying the enum.
    """
    if isinstance(value, bool):
        return value
    if hasattr(value, "value") and not isinstance(value, int | float | str):
        return value.value
    return value
