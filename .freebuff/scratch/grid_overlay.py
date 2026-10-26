#!/usr/bin/env python
"""Debug overlays: draw the lattice grid on archive + shipped devops art.

Red: integer lattice lines (u, v). Magenta dots: tile centers on the floor.
Cyan: floor front edges (v=rh, u=rw). Yellow: wall band outer edge (v=-2.6 / u=-2.6)
and the v=-1 / u=-1 wall base lines. Green: S corner tip + plinth depth line.
Writes devops_archive_grid.png / devops_shipped_grid.png next to the sources.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, write_png  # noqa: E402

SCRATCH = ROOT / ".freebuff" / "scratch"
RED = (255, 64, 64, 255)
MAGENTA = (255, 0, 255, 255)
CYAN = (0, 255, 255, 255)
YELLOW = (255, 240, 0, 255)
GREEN = (0, 255, 128, 255)


def overlay(src: Path, out: Path, cal, rw: int, rh: int) -> None:
    w, h, px = read_png(src)

    def put(x: int, y: int, c) -> None:
        if 0 <= x < w and 0 <= y < h:
            px[y][x] = c

    def line(x0: float, y0: float, x1: float, y1: float, c) -> None:
        steps = int(max(abs(x1 - x0), abs(y1 - y0)) * 2) + 1
        for i in range(steps + 1):
            t = i / steps
            put(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t), c)

    # integer lattice lines u=const (0..rw+1) and v=const (0..rh+1)
    for iu in range(0, rw + 2):
        (x0, y0) = (iu * 32 + cal[0], iu * 16 + cal[1])          # v = -1
        (x1, y1) = ((iu - (rh + 1)) * 32 + cal[0], (iu + rh + 1) * 16 + cal[1])
        line(x0, y0, x1, y1, RED)
    for jv in range(0, rh + 2):
        (x0, y0) = (-jv * 32 + cal[0], jv * 16 + cal[1])          # u = -1
        (x1, y1) = ((rw + 1 - jv) * 32 + cal[0], (rw + 1 + jv) * 16 + cal[1])
        line(x0, y0, x1, y1, RED)

    # wall band outer edges (v = -3, u = -3)
    line(cal[0] + 3 * 32, cal[1] - 3 * 16, (rw + 4) * 32 + cal[0], (rw - 2) * 16 + cal[1], YELLOW)
    line(cal[0] - 3 * 32, cal[1] + 3 * 16, (rw + 4) * 32 - (rh + 3) * 32 + cal[0], (rw + 4 + rh + 3) * 16 + cal[1], YELLOW)

    # front floor edges
    line(cal[0] - rh * 32, cal[1] + rh * 16, (rw - rh) * 32 + cal[0], (rw + rh) * 16 + cal[1], CYAN)
    line((rw - rh) * 32 + cal[0], (rw + rh) * 16 + cal[1], rw * 32 + cal[0], rw * 16 + cal[1], CYAN)

    # tile centers
    for j in range(rh):
        for i in range(rw):
            cx, cy = (i - j) * 32 + cal[0] + 16, (i + j) * 16 + cal[1] + 16
            for dx in range(-2, 3):
                put(cx + dx, cy, MAGENTA)
                put(cx, cy + dx, MAGENTA)

    # S corner + plinth depth marker
    sx, sy = (rw - rh) * 32 + cal[0], (rw + rh) * 16 + cal[1]
    for dy in range(0, 26):
        put(sx, sy + dy, GREEN)

    write_png(out, w, h, px)
    print(f"wrote {out.name} ({w}x{h})")


def main() -> int:
    overlay(
        ROOT / "infra" / "rooms_v1" / "devops.png",
        SCRATCH / "devops_archive_grid.png",
        (295, 172),
        10,
        8,
    )
    overlay(
        ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png",
        SCRATCH / "devops_shipped_grid.png",
        (487, 172),
        12,
        11,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
