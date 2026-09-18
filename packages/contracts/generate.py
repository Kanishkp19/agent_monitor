#!/usr/bin/env python
"""Generate Pydantic models and TypeScript types from `events.schema.json`.

One neutral schema, two generated outputs. Generating Python *from* Python
would leave the TypeScript a second-class derivative and make the schema file
decorative; generating both from one source keeps them provably in step.

    python tasks.py contracts

Outputs (both committed, so a clean clone type-checks without running this):
    services/api/agentshield/domain/generated_events.py
    apps/web/src/types/generated.ts
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = Path(__file__).resolve().parent / "events.schema.json"
PY_OUT = ROOT / "services" / "api" / "agentshield" / "domain" / "generated_events.py"
TS_OUT = ROOT / "apps" / "web" / "src" / "types" / "generated.ts"

BANNER = "GENERATED FROM packages/contracts/events.schema.json -- DO NOT EDIT"

PY_TYPES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool",
            "object": "dict[str, Any]", "array": "list"}
TS_TYPES = {"string": "string", "integer": "number", "number": "number",
            "boolean": "boolean", "object": "Record<string, unknown>"}


def class_name(detail_type: str) -> str:
    """`gate2.decision` -> `Gate2DecisionPayload`."""
    parts = detail_type.replace(".", "_").split("_")
    return "".join(p.capitalize() for p in parts) + "Payload"


def ts_name(detail_type: str) -> str:
    parts = detail_type.replace(".", "_").split("_")
    return "".join(p.capitalize() for p in parts) + "Payload"


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def py_type(spec: dict[str, Any]) -> str:
    if "$ref" in spec:
        return _ref_name(spec["$ref"])
    kind = spec.get("type", "string")
    if kind == "array":
        return f"list[{py_type(spec.get('items', {'type': 'string'}))}]"
    return PY_TYPES.get(kind, "Any")


def ts_type(spec: dict[str, Any]) -> str:
    if "$ref" in spec:
        return _ref_name(spec["$ref"])
    kind = spec.get("type", "string")
    if kind == "array":
        return f"{ts_type(spec.get('items', {'type': 'string'}))}[]"
    if kind == "string" and spec.get("enum"):
        return " | ".join(f"'{v}'" for v in spec["enum"])
    return TS_TYPES.get(kind, "unknown")


def py_default(spec: dict[str, Any]) -> str:
    if "$ref" in spec:
        return " = None"
    kind = spec.get("type", "string")
    return {
        "string": ' = ""',
        "integer": " = 0",
        "number": " = 0.0",
        "boolean": " = False",
        "array": " = Field(default_factory=list)",
        "object": " = Field(default_factory=dict)",
    }.get(kind, " = None")


def generate_python(schema: dict[str, Any]) -> str:
    shared = schema["shared"]
    events = schema["events"]

    uses_any = any(
        py_type(fspec) == "Any"
        for spec in {**shared, **events}.values()
        for fspec in spec["properties"].values()
    )

    lines = [
        '"""Event payload models.',
        "",
        f"{BANNER}",
        "",
        "Regenerate with `python tasks.py contracts`.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
    ]
    if uses_any:
        lines += ["from typing import Any", ""]
    lines += [
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "",
    ]

    for name, spec in shared.items():
        lines.append(f"class {name}(BaseModel):")
        required = set(spec.get("required", []))
        for field, fspec in spec["properties"].items():
            default = "" if field in required else py_default(fspec)
            lines.append(f"    {field}: {py_type(fspec)}{default}")
        lines += ["", ""]

    for detail_type, spec in events.items():
        lines.append(f"class {class_name(detail_type)}(BaseModel):")
        # `model_id` is a real field on several payloads (it is the
        # Bedrock/Converse name and we adopt it verbatim). Pydantic
        # reserves the `model_` prefix by default; every generated
        # payload lifts that so the field name wins over the warning.
        lines.append('    model_config = ConfigDict(protected_namespaces=())')
        doc = spec.get("description")
        lines.append(f'    """`{detail_type}` -- emitted by {spec["emitted_by"]}.')
        if doc:
            lines += ["", f"    {doc}"]
        lines += ['    """', ""]
        required = set(spec.get("required", []))
        for field, fspec in spec["properties"].items():
            default = "" if field in required else py_default(fspec)
            lines.append(f"    {field}: {py_type(fspec)}{default}")
        lines += ["", ""]

    lines.append("EVENT_PAYLOADS: dict[str, type[BaseModel]] = {")
    for detail_type in events:
        lines.append(f'    "{detail_type}": {class_name(detail_type)},')
    lines += ["}", ""]

    lines += [
        "",
        "# Every known `detail_type`. `/ingest/events` validates against this",
        "# registry rather than a hardcoded count -- see DECISIONS-RESOLVED.md C1.",
        "EVENT_TYPES: frozenset[str] = frozenset(EVENT_PAYLOADS)",
        "",
        "",
        "# The six the office renderer reacts to. Everything else still reaches",
        "# the Live Feed; the canvas simply ignores it.",
        "OFFICE_EVENT_TYPES: frozenset[str] = frozenset(",
        "    {",
    ]
    for detail_type, spec in events.items():
        if spec.get("office"):
            lines.append(f'        "{detail_type}",')
    lines += ["    }", ")", ""]

    return "\n".join(lines)


def generate_typescript(schema: dict[str, Any]) -> str:
    shared = schema["shared"]
    events = schema["events"]

    lines = [
        "/**",
        " * Event payload types.",
        " *",
        f" * {BANNER}",
        " *",
        " * Regenerate with `python tasks.py contracts`.",
        " */",
        "",
    ]

    for name, spec in shared.items():
        lines.append(f"export interface {name} {{")
        required = set(spec.get("required", []))
        for field, fspec in spec["properties"].items():
            opt = "" if field in required else "?"
            lines.append(f"  {field}{opt}: {ts_type(fspec)}")
        lines += ["}", ""]

    for detail_type, spec in events.items():
        doc = spec.get("description")
        lines.append("/**")
        lines.append(f" * `{detail_type}` -- emitted by {spec['emitted_by']}.")
        if doc:
            lines += [" *", f" * {doc}"]
        lines.append(" */")
        lines.append(f"export interface {ts_name(detail_type)} {{")
        required = set(spec.get("required", []))
        for field, fspec in spec["properties"].items():
            opt = "" if field in required else "?"
            lines.append(f"  {field}{opt}: {ts_type(fspec)}")
        lines += ["}", ""]

    lines.append("export type EventDetailType =")
    for detail_type in events:
        lines.append(f"  | '{detail_type}'")
    lines.append("")

    lines.append("export interface EventPayloadMap {")
    for detail_type in events:
        lines.append(f"  '{detail_type}': {ts_name(detail_type)}")
    lines += ["}", ""]

    lines.append("export const EVENT_TYPES: readonly EventDetailType[] = [")
    for detail_type in events:
        lines.append(f"  '{detail_type}',")
    lines += ["] as const", ""]

    lines += [
        "/**",
        " * The events the office renderer reacts to.",
        " *",
        " * Everything else still reaches the Live Feed; the canvas ignores it.",
        " * Keeping this list short is what keeps the event pump inside its",
        " * budget of twelve events per frame.",
        " */",
        "export const OFFICE_EVENT_TYPES: ReadonlySet<EventDetailType> = new Set([",
    ]
    for detail_type, spec in events.items():
        if spec.get("office"):
            lines.append(f"  '{detail_type}',")
    lines += ["])", ""]

    lines += [
        "/** The EventBridge-shaped envelope every event travels in. */",
        "export interface EventDetail {",
        "  run_id: string",
        "  seq: number",
        "  sim_ts: number",
        "  employee_id: string | null",
        "  task_id: string | null",
        "  payload: Record<string, unknown>",
        "}",
        "",
        "export interface EventEnvelope {",
        "  id: string",
        "  source: string",
        "  detail_type: EventDetailType",
        "  time: string",
        "  detail: EventDetail",
        "}",
        "",
    ]

    return "\n".join(lines)


def main() -> int:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    PY_OUT.write_text(generate_python(schema), encoding="utf-8")
    TS_OUT.write_text(generate_typescript(schema), encoding="utf-8")

    count = len(schema["events"])
    print(f"generated {count} event payloads")
    print(f"  {PY_OUT.relative_to(ROOT)}")
    print(f"  {TS_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
