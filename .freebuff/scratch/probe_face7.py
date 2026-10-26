#!/usr/bin/env python
"""Final geometry probe for the devops repair.

1. Face x-extent: for intact wall columns (NE u=4,8 / NW v=5,6), scan the
   horizontal op-run at several heights s -> the face's true x span.
2. Column op-runs along the v=0/u=0 anchor lines (H formula check).
3. Donor tile contents in the SHIPPED art: ASCII of interior tiles (0,5)
   and (5,5) at 2px steps, to validate floor donors.
4. Junk map of the shipped art south band before repair.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
CAL = (487, 172)

def to_px(u, v):
    return ((u - v) * 32 + CAL[0], (u + v) * 16 + CAL[1])

w, h, px = read_png(SHIP)

def op_run_row(y: int, x0: int, x1: int):
    runs, cur = [], None
    for x in range(max(0, x0), min(w, x1)):
        s = "op" if px[y][x][3] >= 40 else "."
        if cur and cur[0] == s:
            cur[2] = x
        else:
            if cur:
                runs.append(cur)
            cur = [s, x, x]
    if cur:
        runs.append(cur)
    return [r for r in runs if r[0] == "op"]

print("== 1. face x-extent at fixed heights (intact NE wall) ==")
for u in (4.0, 6.0, 8.0):
    bx, by = to_px(u, 0.0)
    H = 5.7 * u + 10.3
    for s in (10, 20, 30, 45):
        if s >= H - 2:
            continue
        y = int(by - s)
        runs = op_run_row(y, int(bx) - 60, int(bx) + 60)
        desc = ", ".join(f"{r[1]-int(bx):+d}..{r[2]-int(bx):+d}" for r in runs[:4])
        print(f"  NE u={u} s={s}: op x-offsets [{desc}]")

print("== face x-extent (intact NW wall) ==")
for v in (5.0, 6.5):
    bx, by = to_px(0.0, v)
    H = 8.0 * v + 9.0
    for s in (10, 20, 30, 45):
        if s >= H - 2:
            continue
        y = int(by - s)
        runs = op_run_row(y, int(bx) - 60, int(bx) + 60)
        desc = ", ".join(f"{r[1]-int(bx):+d}..{r[2]-int(bx):+d}" for r in runs[:4])
        print(f"  NW v={v} s={s}: op x-offsets [{desc}]")

print("== 3. shipped interior tiles (floor donors) ==")
sys.path.insert(0, "/Users/kanishk_pandey/Desktop/as/.freebuff/scratch")
from ascii_map import classify  # noqa: E402

def tile_ascii(i, j, step=3):
    X0, Y0 = to_px(i + 0.1, j + 0.1)
    print(f"  tile ({i},{j}) origin~({X0:.0f},{Y0:.0f})")
    for yy in range(0, 36, step):
        row = ""
        for xx in range(0, 62, step):
            x, y = int(X0 + xx), int(Y0 + yy)
            row += classify(*px[y][x]) if (0 <= x < w and 0 <= y < h) else "?"
        print(f"    {row}")

tile_ascii(0, 5)
tile_ascii(5, 5)
