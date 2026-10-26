#!/usr/bin/env python
"""Pixel-level trace of clone_tile on tile (10,9)."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
sys.path.insert(0, str(ROOT))
from extract_furniture import read_png
from infra.scripts.repair_devops import clone_tile, to_px  # noqa: E402
sys.path.insert(0, "/Users/kanishk_pandey/Desktop/as/.freebuff/scratch")
from ascii_map import classify  # noqa: E402

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
w, h, px = read_png(SHIP)

X0, Y0 = to_px(10.3, 9.3)
Xi, Yi = int(X0), int(Y0)
print(f"tile (10,9) sample anchor px=({Xi},{Yi})")
print("before (region 519,489 -> +40):")
for y in range(Yi - 6, Yi + 30, 4):
    print(f"  {y}: " + "".join(classify(*px[y][x]) for x in range(Xi - 8, Xi + 34, 2)))
print("sample px before:", [px[Yi][Xi - 4 + k * 2][:3] for k in range(4)])

n = clone_tile(px, w, h, 10, 9, 7, 6)
print("cloned:", n)
print("after:")
for y in range(Yi - 6, Yi + 30, 4):
    print(f"  {y}: " + "".join(classify(*px[y][x]) for x in range(Xi - 8, Xi + 34, 2)))
print("sample px after: ", [px[Yi][Xi - 4 + k * 2][:3] for k in range(4)])

Sx, Sy = to_px(7.3, 6.3)
print(f"donor (7,6) anchor px=({int(Sx)},{int(Sy)}):")
for y in range(int(Sy) - 6, int(Sy) + 30, 4):
    print(f"  {y}: " + "".join(classify(*px[y][x]) for x in range(int(Sx) - 8, int(Sx) + 34, 2)))
