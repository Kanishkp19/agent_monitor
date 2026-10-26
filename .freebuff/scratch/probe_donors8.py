#!/usr/bin/env python
"""Donor-eligibility map of the shipped devops interior tiles.

A tile is DONOR-ELIGIBLE (clean floor) if >=97% of a dense quad sample is
floorish: warm sand (r-b>=18, r>=55), chevron blue (b>=r+6), or dark
grout/base (lum<=42). Chair/rack grays fail all three.
Prints an eligibility map + mean tones.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
CAL = (487, 172)
RW, RH = 12, 11

def to_px(u, v):
    return ((u - v) * 32 + CAL[0], (u + v) * 16 + CAL[1])

w, h, px = read_png(SHIP)

def floorish(r, g, b, a):
    if a < 200:
        return False
    lum = (r * 3 + g * 6 + b) // 10
    warm = r - b >= 18 and r >= 55
    blue = b >= r + 6 and b >= 55
    dark = lum <= 42
    return warm or blue or dark

elig = [[False] * RW for _ in range(RH)]
means = {}
for j in range(RH):
    for i in range(RW):
        tot = ok = 0
        acc = [0, 0, 0]
        nok = 0
        for iy in range(14):
            for ix in range(14):
                du, dv = 0.05 + 0.065 * ix, 0.05 + 0.065 * iy
                X, Y = to_px(i + du, j + dv)
                xi, yi = int(X), int(Y)
                if not (0 <= xi < w and 0 <= yi < h):
                    continue
                r, g, b, a = px[yi][xi]
                tot += 1
                if floorish(r, g, b, a):
                    ok += 1
                    acc[0] += r; acc[1] += g; acc[2] += b
                    nok += 1
        elig[j][i] = tot > 0 and ok / tot >= 0.97
        means[(i, j)] = (acc[0] // nok, acc[1] // nok, acc[2] // nok) if nok else (0, 0, 0)

print("eligibility (D=donor-eligible, .=not):")
print("     " + "".join(str(i // 10) for i in range(RW)))
print("     " + "".join(str(i % 10) for i in range(RW)))
for j in range(RH):
    print(f"  {j:2d} " + "".join("D" if elig[j][i] else "." for i in range(RW)))

print("\nmean tones of eligible tiles:")
for j in range(RH):
    for i in range(RW):
        if elig[j][i]:
            print(f"  ({i:2d},{j:2d}) {means[(i, j)]}")
