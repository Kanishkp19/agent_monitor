#!/usr/bin/env python
"""True wall top-edge scan for the three rooms.

For each wall (NE = v=0 plane along u; NW = u=0 plane along v) scan each
0.25-tile column DOWNWARD from high above the base; the first opaque pixel
is the real top edge. Print per 0.5 tile so breaks/holes are visible, plus
a robust linear fit over the columns whose top edge lies on a straight line.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png  # noqa: E402

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"

ROOMS = {
    "managers":     {"cal": (520, 172), "rw": 12, "rh": 11},
    "ceo_office":   {"cal": (424, 172), "rw": 12, "rh": 10},
    "meeting_room": {"cal": (423, 173), "rw": 20, "rh": 12},
}


def top_edge(px, w, h, x, y_from, y_to):
    """First opaque pixel scanning down from y_from to y_to at column x."""
    x = int(x)
    for y in range(max(0, int(y_from)), min(h, int(y_to))):
        if px[y][x][3] >= 40:
            return float(y)
    return None


def scan_wall(w, h, px, cal, axis, a_max, band=19.2):
    """Per 0.25-tile: (a, top_y, face_ok) using the face-band mid column."""
    out = []
    a = 0.0
    while a <= a_max - 0.01:
        if axis == "u":          # NE face band: x in [32a+cal, +band]
            x = 32 * a + cal[0] + band * 0.45
            yb = 16 * a + cal[1]
        else:                    # NW face band: x in [-band, cal-32a]
            x = cal[0] - 32 * a - band * 0.45
            yb = 16 * a + cal[1]
        t = top_edge(px, w, h, x, yb - 190, yb + 2)
        out.append((a, t))
        a += 0.25
    return out


def fit(pts):
    """Robust linear fit top_y = c0 + c1*a on the dominant straight run."""
    best = None
    for lo in range(0, len(pts) - 5):
        for hi in range(lo + 6, len(pts) + 1):
            seg = pts[lo:hi]
            if any(t is None for _, t in seg):
                continue
            n = len(seg)
            sx = sum(p[0] for p in seg)
            sy = sum(p[1] for p in seg)
            sxx = sum(p[0] * p[0] for p in seg)
            sxy = sum(p[0] * p[1] for p in seg)
            d = n * sxx - sx * sx
            if d == 0:
                continue
            c1 = (n * sxy - sx * sy) / d
            c0 = (sy - c1 * sx) / n
            res = max(abs(t - (c0 + c1 * a)) for a, t in seg)
            if res <= 3.5:
                score = n * 10 - (hi - lo) * 0  # longest run wins
                if best is None or (hi - lo) > (best[1] - best[0]):
                    best = (lo, hi, c0, c1)
    return best


def main() -> int:
    for rid, cfg in ROOMS.items():
        w, h, px = read_png(ASSETS / f"{rid}.png")
        cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
        print(f"\n===== {rid} {w}x{h} cal={cal} {rw}x{rh} =====")
        for axis, a_max, name in (("u", rw, "NE"), ("v", rh, "NW")):
            scan = scan_wall(w, h, px, cal, axis, a_max)
            pts = [(a, t) for a, t in scan]
            b = fit(pts)
            if b:
                lo, hi, c0, c1 = b
                a_lo, a_hi = pts[lo][0], pts[hi - 1][0]
                print(f"  {name}: straight run a in [{a_lo:.2f},{a_hi:.2f}]  "
                      f"top_y = {c0:.1f} {c1:+.2f}a")
                row1, row2 = "    a : ", "    top: "
                for a, t in scan:
                    if abs(a * 2 - round(a * 2)) < 0.01:   # every 0.5
                        row1 += f"{a:6.1f}"
                        row2 += f"{t:6.0f}" if t is not None else "   none"
                print(row1)
                print(row2)
                off = [(a, t) for a, t in scan
                       if t is not None and (a < a_lo - 0.01 or a > a_hi + 0.01)
                       and abs(t - (c0 + c1 * a)) > 6]
                nones = [a for a, t in scan if t is None]
                if off:
                    spans = []
                    for a, _ in off:
                        if spans and a - spans[-1][1] <= 0.3:
                            spans[-1][1] = a
                        else:
                            spans.append([a, a])
                    print(f"    off-fit spans: " + ", ".join(f"[{lo2:.2f},{hi2:.2f}]" for lo2, hi2 in spans))
                if nones:
                    print(f"    no-wall columns (void): {nones}")
            else:
                print(f"  {name}: no straight run found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
