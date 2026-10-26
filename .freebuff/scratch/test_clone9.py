#!/usr/bin/env python
"""Isolated test: does clone_tile actually change tile (10,9)?"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
sys.path.insert(0, str(ROOT))
from extract_furniture import read_png
from infra.scripts.repair_devops import clone_tile, to_px, DONORS  # noqa: E402

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
w, h, px = read_png(SHIP)

def stats(i, j):
    vals = []
    for iy in range(4, 14):
        for ix in range(4, 14):
            X, Y = to_px(i + 0.06 + 0.058 * ix, j + 0.06 + 0.058 * iy)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] >= 200:
                vals.append((px[yi][xi][0] * 3 + px[yi][xi][1] * 6 + px[yi][xi][2]) // 10)
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return f"mean {m:.0f} sd {sd:.0f} n {len(vals)}"

print("target (10,9) before:", stats(10, 9))
si, sj = DONORS[(10 * 7 + 9 * 5) % len(DONORS)]
print("donor:", (si, sj), "donor stats:", stats(si, sj))
n = clone_tile(px, w, h, 10, 9, si, sj)
print("cloned px:", n)
print("target (10,9) after: ", stats(10, 9))
