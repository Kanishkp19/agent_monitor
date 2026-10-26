#!/usr/bin/env python
"""Measure the intact wall structure of the shipped devops art.

For sample lattice positions along the NE wall (v=0 face) and NW wall
(u=0 face), print the vertical runs of opaque/void pixels in the art column
through the wall, so the repair painter can copy the real geometry:
face height, cap thickness, exact top edge slope, base line.
Also: per-tile edge-contrast stats to separate junk tiles from smooth floor.
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

def col_runs(x: int, y0: int, y1: int):
    runs = []
    cur = None
    for y in range(y0, min(y1, h)):
        a = px[y][x][3]
        state = "op" if a >= 40 else "vd"
        if cur and cur[0] == state:
            cur[2] = y
        else:
            if cur:
                runs.append(cur)
            cur = [state, y, y]
    if cur:
        runs.append(cur)
    return runs

print("== NE wall (base v=0, column through x of u) ==")
for u in (1.0, 3.0, 5.0, 7.0, 8.5, 9.5, 10.5, 11.5):
    bx, by = to_px(u, 0.0)
    x = int(bx)
    runs = col_runs(x, int(by) - 130, int(by) + 4)
    desc = ", ".join(f"{r[0]}:{r[1]-int(by)}..{r[2]-int(by)}" for r in runs)
    print(f"  u={u:4.1f} base=({bx:.0f},{by:.0f}): {desc}")

print("== NW wall (base u=0, column through x of v) ==")
for v in (1.0, 3.0, 5.0, 6.5, 7.5, 8.5, 9.5, 10.5):
    bx, by = to_px(0.0, v)
    x = int(bx)
    runs = col_runs(x, int(by) - 130, int(by) + 4)
    desc = ", ".join(f"{r[0]}:{r[1]-int(by)}..{r[2]-int(by)}" for r in runs)
    print(f"  v={v:4.1f} base=({bx:.0f},{by:.0f}): {desc}")

# horizontal run through the wall at a fixed height to see thickness/cap
print("== horizontal cut at s=40 above the NE base line (u=5) ==")
bx, by = to_px(5.0, 0.0)
y = int(by) - 40
row = []
for x in range(int(bx) - 40, min(int(bx) + 140, w)):
    row.append("op" if px[y][x][3] >= 40 else ".")
s = "".join(row)
print(f"  y={y}: {s}")

print("== horizontal cut at s=70 (above face?) ==")
y = int(by) - 70
row = []
for x in range(int(bx) - 40, min(int(bx) + 140, w)):
    row.append("op" if px[y][x][3] >= 40 else ".")
print(f"  y={y}: {''.join(row)}")

# tile edge-contrast stats
print("== tile edge-contrast (junk detector) ==")
RW, RH = 12, 11
for j in range(RH):
    line = []
    for i in range(RW):
        X0, Y0 = to_px(i + 0.5, j + 0.5)
        vals = []
        for iy in range(-10, 11, 2):
            for ix in range(-10, 11, 2):
                x, y = int(X0) + ix, int(Y0) + iy
                if 0 <= x < w and 0 <= y < h and px[y][x][3] >= 200:
                    lum = (px[y][x][0] * 3 + px[y][x][1] * 6 + px[y][x][2]) // 10
                    vals.append(lum)
        if len(vals) < 30:
            line.append("  ??  ")
            continue
        vals.sort()
        med = vals[len(vals) // 2]
        contrast = sum(1 for vv in vals if abs(vv - med) > 30) / len(vals)
        mean = sum(vals) // len(vals)
        line.append(f"{contrast:4.2f}/{mean:3d}")
    print(f"  v={j:2d}: " + " ".join(line))
