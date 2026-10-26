#!/usr/bin/env python
"""Render a room PNG as an ASCII map so the repair can be verified in-terminal.

    python ascii_map.py <png> [x0 y0 x1 y1 step]

Class legend: ' ' void/transparent, '.' very dark, '~' blue-gray (chevron),
'#' bright brick, '%' dark brick, '+' light sand floor, '-' dim sand floor,
'"' green (plants/rack LEDs), 'o' neutral gray (chairs/racks), '?' other.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png


def classify(r: int, g: int, b: int, a: int) -> str:
    if a < 40:
        return " "
    lum = (r * 3 + g * 6 + b) // 10
    if lum < 35:
        return "."
    if b > r + 12:
        return "~"
    if g >= r + 8 and g > b:
        return '"'
    if r - b > 45 and r > 150:
        return "#"
    if r - b > 30:
        return "%"
    if r - b > 12:
        return "+" if lum > 135 else "-"
    return "o"


def main() -> None:
    png = Path(sys.argv[1])
    x0, y0, x1, y1, step = 0, 0, 10**9, 10**9, 8
    if len(sys.argv) >= 6:
        x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
        step = int(sys.argv[6]) if len(sys.argv) >= 7 else 8

    w, h, px = read_png(png)
    x1, y1 = min(x1, w), min(y1, h)
    print(f"{png.name} {w}x{h}  region ({x0},{y0})-({x1},{y1}) step {step}")
    header = "".join(str((x0 + x * step) // 100 % 10) if (x0 + x * step) % 100 < step else " "
                     for x in range((x1 - x0) // step))
    print("     " + header)
    for y in range(y0, y1, step):
        row = "".join(classify(*px[min(y, h - 1)][min(x, w - 1)])
                      for x in range(x0, x1, step))
        print(f"{y:4d} {row}")


if __name__ == "__main__":
    main()
