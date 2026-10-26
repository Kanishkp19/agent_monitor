#!/usr/bin/env python
"""Per-tile signature map for the three rooms: mean lum / sd / opaque%,
with footprint-rect and grown-band overlays, to classify junk tiles."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"
GEN = ROOT / "apps" / "web" / "src" / "game" / "engine" / "footprints.generated.ts"

ROOMS = {
    "managers":     (12, 11, (520, 172), (10, 8)),
    "ceo_office":   (12, 10, (424, 172), (10, 8)),
    "meeting_room": (20, 12, (423, 173), (16, 12)),
}

# parse footprints.generated.ts (a single JSON object literal)
src = GEN.read_text()
start = src.index("{")
json_text = src[start:].rstrip().rstrip(";")
FOOT = json.loads(json_text)


def to_px(u, v, cal):
    return ((u - v) * 32 + cal[0], (u + v) * 16 + cal[1])


for rid, (rw, rh, cal, (grw, grh)) in ROOMS.items():
    w, h, px = read_png(ASSETS / f"{rid}.png")
    rects = FOOT.get(rid, [])
    print(f"\n===== {rid} {w}x{h} (grown bands: u>={grw} or v>={grh}; F=footprint) =====")
    print("     " + "".join(str(i // 10) for i in range(rw)))
    print("     " + "".join(str(i % 10) for i in range(rw)))
    for j in range(rh):
        line = []
        for i in range(rw):
            vals = []
            for iy in range(4, 15, 2):
                for ix in range(4, 15, 2):
                    X, Y = to_px(i + 0.06 + 0.062 * ix, j + 0.06 + 0.062 * iy, cal)
                    xi, yi = int(X), int(Y)
                    if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] >= 200:
                        vals.append((px[yi][xi][0] * 3 + px[yi][xi][1] * 6 + px[yi][xi][2]) // 10)
            in_fp = any(x <= i < x + ww and y <= j < y + dd for (x, y, ww, dd) in rects)
            grown = i >= grw or j >= grh
            if len(vals) < 8:
                tag = " "  # void
            else:
                m = sum(vals) / len(vals)
                sd = (sum((vv - m) ** 2 for vv in vals) / len(vals)) ** 0.5
                tag = f"{int(m):3d}/{sd:02.0f}"
            line.append(f"{tag:>7}" + ("F" if in_fp else " ") + ("*" if grown else " "))
        print(f"  {j:2d} " + "|".join(line))
