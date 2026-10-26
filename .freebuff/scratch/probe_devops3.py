#!/usr/bin/env python
"""Probe #3: archive devops wall stripes — find clean donor zones in IMAGE space.

For the back (NE) wall: scan vertical stripes anchored on the base line
(u = 0..10 step 0.25, base pixel = to_px(u, 0, cal_a)), classify pixels upward
from base-96px to base: brick / other. Clean stripe = >=92% brick-ish.
Same for the left (NW) wall along v = 0..8.
Prints per-stripe rows so donor zones can be picked visually.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png  # noqa: E402

ARC = ROOT / "infra" / "rooms_v1" / "devops.png"
CAL = (295, 172)
TW_HALF, TH_HALF = 32, 16


def to_px(u: float, v: float) -> tuple[float, float]:
    return ((u - v) * TW_HALF + CAL[0], (u + v) * TH_HALF + CAL[1])


def is_bricky(r: int, g: int, b: int, a: int) -> bool:
    if a < 40:
        return False
    # brick red/brown family incl. mortar (darker) and cap highlight
    return r > g >= b - 6 and r - b > 18


def main() -> int:
    w, h, px = read_png(ARC)
    print(f"archive canvas {w}x{h}")

    print("\n== NE (back) wall stripes: column quality upward from base ==")
    print("  u     %brick  rows(12) top-down: b=brick o=other .=void")
    for uq in range(0, 41):
        u = uq / 4
        bx, by = to_px(u, 0.0)
        rows = []
        brick = tot = 0
        for dy in range(-96, 2, 8):
            x, y = int(bx), int(by + dy)
            if 0 <= x < w and 0 <= y < h:
                r, g, b, a = px[y][x]
                ok = is_bricky(r, g, b, a)
                rows.append("b" if ok else ("." if a < 40 else "o"))
                tot += 1
                brick += ok
        print(f"  {u:5.2f}  {100 * brick // max(1, tot):4d}   {''.join(rows)}")

    print("\n== NW (left) wall stripes: column quality upward from base ==")
    print("  v     %brick  rows(12) top-down")
    for vq in range(0, 33):
        v = vq / 4
        bx, by = to_px(0.0, v)
        rows = []
        brick = tot = 0
        for dy in range(-96, 2, 8):
            x, y = int(bx), int(by + dy)
            if 0 <= x < w and 0 <= y < h:
                r, g, b, a = px[y][x]
                ok = is_bricky(r, g, b, a)
                rows.append("b" if ok else ("." if a < 40 else "o"))
                tot += 1
                brick += ok
        print(f"  {v:5.2f}  {100 * brick // max(1, tot):4d}   {''.join(rows)}")

    # wall top edge: find first opaque pixel above base at a few u/v
    def top_of_wall(bx: float, by: float) -> int:
        for dy in range(-140, 0):
            x, y = int(bx), int(by + dy)
            if 0 <= x < w and 0 <= y < h:
                r, g, b, a = px[y][x]
                if a >= 40:
                    return dy
        return 0

    print("\n== wall top edge dy (image px above base) ==")
    for u in (2.0, 5.0, 8.0, 9.5):
        bx, by = to_px(u, 0.0)
        print(f"  NE u={u:4.1f}: top {top_of_wall(bx, by)}px")
    for v in (2.0, 5.0, 7.0):
        bx, by = to_px(0.0, v)
        print(f"  NW v={v:4.1f}: top {top_of_wall(bx, by)}px")
    return 0


if __name__ == "__main__":
    sys.exit(main())
