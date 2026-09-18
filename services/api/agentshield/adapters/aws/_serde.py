"""DynamoDB value conversion.

DynamoDB's Number type is decimal, and boto3 refuses to serialise a Python
`float` because binary floating point cannot round-trip through it exactly.
Every cost figure in this product is a float, so the conversion happens here,
once, rather than at forty call sites.

The asymmetry is deliberate: floats become `Decimal` on the way in, and
`Decimal` becomes `int` or `float` on the way out. A counter that went in as
`23` comes back as `23`, not `Decimal('23')` and not `23.0` -- it crosses a
JSON boundary into the UI, where the three render differently.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# DynamoDB accepts 38 significant digits. Money and token counts are nowhere
# near that, so rounding at 10 decimal places is lossless here and keeps the
# stored form readable.
_QUANTum = Decimal("1E-10")


def to_dynamo(value: Any) -> Any:
    """Python -> DynamoDB-safe. Recurses through dicts and lists."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value)).quantize(_QUANTum).normalize()
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    """DynamoDB -> Python. `Decimal` collapses back to `int` where exact."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [from_dynamo(v) for v in value]
    return value
