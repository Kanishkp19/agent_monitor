#!/usr/bin/env python
"""Render 3x magnified crops of the damaged zones with lattice ticks.

Zones:
  A: NE wall far end   u in [8.0, 12.8], dy in [-84, +8]   (shelf end, notch, fragment)
  B: NW wall far end   v in [6.0, 11.6], dx in [-84, +8]   (hole, seam, corner)
  C: south floor band  u in [8.5, 12.2], v in [7.0, 11.4]  (chair junk, plinth)
Each crop: magenta ticks every 0.5 tile along lattice lines, red u/v labels.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, write_png  # noqa: E402

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
OUT = ROOT / ".freebuff" / "scratch"
CAL = (487, 172)
TW_HALF, TH_HALF = 32, 16
S = 3  # zoom

MAGENTA = (255, 0, 255, 255)
RED = (255, 60, 60, 255)


def to_px(u: float, v: float) -> tuple[float, float]:
    return ((u - v) * TW_HALF + CAL[0], (u + v) * TH_HALF + CAL[1])


def render(name: str, zone: tuple[float, float, float, float], mode: str) -> None:
    """mode 'ne': axes (u, dy px); 'nw': axes (v, dx px); 's': axes (u, v)."""
    u0, u1, a0, a1 = zone
    w, h, px = read_png(SHIP)

    # sample source grid — wall modes: 8/u-unit, 0.5px steps in dy;
    # south mode: 8/unit both axes
    step = 0.5 if mode in ("ne", "nw") else 0.125
    cols = int((u1 - u0) * 8) + 1
    rows = int((a1 - a0) / step) + 1
    grid = [[(0, 0, 0, 0)] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            uu = u0 + c / 8
            aa = a0 + r * step
            if mode == "ne":
                X, Y = to_px(uu, 0.0)
                xi, yi = int(X), int(Y + aa)
            elif mode == "nw":
                X, Y = to_px(0.0, uu)
                xi, yi = int(X + aa), int(Y)
            else:
                X, Y = to_px(uu, aa)
                xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h:
                grid[r][c] = px[yi][xi]

    OW, OH = cols * S, rows * S
    out = [[(24, 24, 30, 255)] * OW for _ in range(OH)]
    for r in range(rows):
        for c in range(cols):
            r_, g_, b_, a_ = grid[r][c]
            fill = (r_, g_, b_, 255) if a_ >= 40 else (24, 24, 30, 255)
            for yy in range(r * S, r * S + S):
                row = out[yy]
                for xx in range(c * S, c * S + S):
                    row[xx] = fill

    def mark(c: int, r: int, col) -> None:
        for yy in range(max(0, r * S - 1), min(OH, r * S + S + 1)):
            for xx in range(max(0, c * S - 1), min(OW, c * S + S + 1)):
                out[yy][xx] = col

    # lattice ticks: u integers (dense vertical magenta line)
    for ui in range(int(u0) - 1, int(u1) + 2):
        c = round((ui - u0) * 8)
        if 0 <= c < cols:
            for r in range(0, rows, 3):
                mark(c, r, MAGENTA)
    # horizontal ticks every 8px in wall modes (dy), 0.5 unit in south mode
    a_tick = 8 if mode in ("ne", "nw") else 0.5
    a_val = a0
    while a_val <= a1:
        r = int(round((a_val - a0) / step))
        if 0 <= r < rows:
            for c in range(0, cols, 3):
                mark(c, r, MAGENTA)
        a_val += a_tick

    write_png(OUT / f"{name}.png", OW, OH, out)
    print(f"wrote {name}.png {OW}x{OH}  (zone u {u0}..{u1}, a {a0}..{a1})")


def main() -> int:
    render("crop_ne_wall", (8.0, 12.8, -84.0, 8.0), "ne")
    render("crop_nw_wall", (6.0, 11.6, -84.0, 8.0), "nw")
    return 0


if __name__ == "__main__":
    sys.exit(main())
