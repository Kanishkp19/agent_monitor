#!/usr/bin/env python
"""Probe the devops room art: classify per-tile floor purity in lattice coords.

Prints an ASCII map for both the ARCHIVE (10x8) and the SHIPPED (12x11) art:
  . = clean floor, o = non-floor blob on the floor plane, W = wall region,
  # = outside canvas / void
Also locates the dark blobs (chairs) and the wall band extents.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, sample_floor_palette, tile_center_px, wall_region_tester, near, BG  # noqa: E402

ARC = ROOT / "infra" / "rooms_v1"
SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"

ARC_ROOM = {"o": (0, 0), "s": (10, 8), "cal": (295, 172)}
SHIP_ROOM = {"o": (0, 0), "s": (12, 11), "cal": (487, 172)}

TW_HALF, TH_HALF = 32, 16


def to_px(u: float, v: float, cal) -> tuple[float, float]:
    return ((u - v) * TW_HALF + cal[0], (u + v) * TH_HALF + cal[1])


def back(X: float, Y: float, cal) -> tuple[float, float]:
    a = (X - cal[0]) / TW_HALF
    b = (Y - cal[1]) / TH_HALF
    return ((a + b) / 2, (b - a) / 2)


DIAMOND_OFFS = [
    (0.06 + 0.09 * ix, 0.06 + 0.09 * iy) for iy in range(10) for ix in range(10)
]


def classify(path: Path, room: dict) -> list[list[str]]:
    rw, rh = room["s"]
    w, h, px = read_png(path)
    floor = sample_floor_palette(px, w, h, room)
    base = list(floor)
    for k in (0.85, 0.7, 0.55, 0.45):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base]
    is_wall = wall_region_tester(room)
    grid = [["#"] * rw for _ in range(rh)]
    for j in range(rh):
        for i in range(rw):
            wall_n = floor_n = non_n = void_n = 0
            for du, dv in DIAMOND_OFFS:
                X, Y = to_px(i + du, j + dv, room["cal"])
                xi, yi = int(X), int(Y)
                if not (0 <= xi < w and 0 <= yi < h):
                    void_n += 1
                    continue
                if is_wall(xi, yi):
                    wall_n += 1
                    continue
                r, g, b, a = px[yi][xi]
                if a < 40 or (abs(r - BG[0]) < 14 and abs(g - BG[1]) < 14 and abs(b - BG[2]) < 14):
                    void_n += 1
                elif near((r, g, b), floor, 22):
                    floor_n += 1
                else:
                    non_n += 1
            n = wall_n + floor_n + non_n + void_n
            if n == 0:
                grid[j][i] = "?"
                continue
            if wall_n / n > 0.4:
                grid[j][i] = "W"
            elif non_n / n > 0.35:
                grid[j][i] = "o"
            elif floor_n / n > 0.55:
                grid[j][i] = "."
            else:
                grid[j][i] = ","
    return grid


def show(title: str, grid: list[list[str]]) -> None:
    print(f"\n== {title} ==")
    for j, row in enumerate(grid):
        print(f"  {j:2d} {''.join(row)}")
    print("     " + "".join(str(i % 10) for i in range(len(grid[0]))))


def dark_blobs(path: Path, cal, rw: int, rh: int) -> None:
    """Find very dark pixels on/below the floor plane (chairs are near-black)."""
    w, h, px = read_png(path)
    hits: dict[tuple[int, int], int] = {}
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[y][x]
            if a >= 200 and (r + g + b) / 3 < 38:
                u, v = back(x + 0.5, y + 0.5, cal)
                if 0 <= u <= rw and 0 <= v <= rh + 1.2:
                    key = (int(u * 2), int(v * 2))
                    hits[key] = hits.get(key, 0) + 1
    cols: dict[int, int] = {}
    for (iu, iv), n in hits.items():
        if n > 8:
            cols.setdefault(iv, 0)
            cols[iv] += n
    print("\n== dark pixels (chairs/shadows) by v-band (x2 lattice) ==")
    for iv in sorted(cols):
        print(f"  v~{iv / 2:5.1f}  {cols[iv]:6d}px")


def main() -> int:
    show("ARCHIVE devops 10x8 (infra/rooms_v1/devops.png)", classify(ARC / "devops.png", ARC_ROOM))
    show("SHIPPED devops 12x11 (public/assets/office/rooms/devops.png)", classify(SHIP / "devops.png", SHIP_ROOM))
    dark_blobs(ARC / "devops.png", ARC_ROOM["cal"], 10, 8)
    dark_blobs(SHIP / "devops.png", SHIP_ROOM["cal"], 12, 11)

    # wall band extents in the shipped art: sample along u=-0.5 and v=-0.5
    w, h, px = read_png(SHIP / "devops.png")
    for label, pts in (
        ("back wall v=-0.6..0 (u sweep)", [(u, -0.6) for u in (0, 2, 4, 6, 8, 10, 11.5)]),
        ("left wall u=-0.6..0 (v sweep)", [(-0.6, v) for v in (0, 2, 4, 6, 8, 10, 11.5)]),
    ):
        print(f"\n== {label} ==")
        for (u, v) in pts:
            X, Y = to_px(u, v, SHIP_ROOM["cal"])
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h:
                r, g, b, a = px[yi][xi]
                print(f"  u={u:5.1f} v={v:5.1f} -> ({xi},{yi}) rgba=({r},{g},{b},{a})")
            else:
                print(f"  u={u:5.1f} v={v:5.1f} -> ({xi},{yi}) OUTSIDE canvas {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
