#!/usr/bin/env python
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
print(f"{w}x{h}")

for (i, j) in [(0, 10), (1, 9), (5, 10), (11, 10), (0, 7), (4, 8), (10, 6), (11, 3)]:
    X, Y = to_px(i + 0.5, j + 0.5)
    xi, yi = int(X), int(Y)
    colors = [px[yi + dy][xi + dx][:3] for dy in (-4, 0, 4) for dx in (-4, 0, 4)]
    mean = tuple(sum(c[k] for c in colors) // len(colors) for k in range(3))
    print(f"tile ({i:2d},{j:2d}) mean={mean}  samples={colors[::4]}")

# histogram of the south band floor-ish colors
from collections import Counter
cnt = Counter()
for j in (9, 10):
    for i in range(12):
        for iy in range(4):
            for ix in range(4):
                X, Y = to_px(i + 0.15 + 0.23 * ix, j + 0.15 + 0.23 * iy)
                xi, yi = int(X), int(Y)
                r, g, b, a = px[yi][xi]
                if a >= 200:
                    cnt[(r // 16 * 16, g // 16 * 16, b // 16 * 16)] += 1
print("\ntop colors in south band:")
for c, n in cnt.most_common(12):
    print(f"  {c}: {n}")
