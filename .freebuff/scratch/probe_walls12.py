#!/usr/bin/env python
"""Per-room wall geometry fit: H(a) = m*a + c for NE (v=0) and NW (u=0)
faces, fit from intact columns; plus damage-zone ASCII eyeballs."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"
ROOMS = {
    "managers":     (12, 11, (520, 172)),
    "ceo_office":   (12, 10, (424, 172)),
    "meeting_room": (20, 12, (423, 173)),
}


def to_px(u, v, cal):
    return ((u - v) * 32 + cal[0], (u + v) * 16 + cal[1])


for rid, (rw, rh, cal) in ROOMS.items():
    w, h, px = read_png(ASSETS / f"{rid}.png")
    print(f"\n===== {rid} {w}x{h} =====")

    def top_of(x, y_base):
        for dy in range(-160, 1):
            y = int(y_base) + dy
            if 0 <= y < h and px[y][int(x)][3] >= 40:
                return -dy
        return None

    print("  NE face top-edge samples (u: H px):")
    pts = []
    for u10 in range(5, rw * 10, 15):
        u = u10 / 10
        bx, by = to_px(u, 0.0, cal)
        if not (0 <= int(bx) < w):
            continue
        t = top_of(bx, by)
        if t:
            pts.append((u, t))
    print("   ", ", ".join(f"{u:.1f}:{t}" for u, t in pts))
    if len(pts) >= 4:
        n = len(pts)
        mu = sum(p[0] for p in pts) / n
        mt = sum(p[1] for p in pts) / n
        m = sum((p[0] - mu) * (p[1] - mt) for p in pts) / sum((p[0] - mu) ** 2 for p in pts)
        print(f"    fit NE: H = {m:.2f}u + {mt - m * mu:.1f}")

    print("  NW face top-edge samples (v: H px):")
    pts = []
    for v10 in range(5, rh * 10, 15):
        v = v10 / 10
        bx, by = to_px(0.0, v, cal)
        if not (0 <= int(bx) < w):
            continue
        t = top_of(bx, by)
        if t:
            pts.append((v, t))
    print("   ", ", ".join(f"{v:.1f}:{t}" for v, t in pts))
    if len(pts) >= 4:
        n = len(pts)
        mv = sum(p[0] for p in pts) / n
        mt = sum(p[1] for p in pts) / n
        m = sum((p[0] - mv) * (p[1] - mt) for p in pts) / sum((p[0] - mv) ** 2 for p in pts)
        print(f"    fit NW: H = {m:.2f}v + {mt - m * mv:.1f}")
