#!/usr/bin/env python
"""Per-room measurement for the generalized room repair.

For each room print:
  1. NE wall (v=0, along u in [0,RW]): per-0.25-tile top-edge fit -> linear
     fit on the intact span, residuals -> broken span; face brick coverage
     per 0.5 tile (to find window/lamp-free clone source spans).
  2. NW wall (u=0, along v in [0,RH]): same.
  3. Grown-band floor tiles: junk classification (void px inside the tile
     diamond + chevron-family signature) and clean donor candidates
     (97% floorish quads vs the room's own floor tone).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png  # noqa: E402

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"

ROOMS = {
    "managers":     {"cal": (520, 172), "rw": 12, "rh": 11, "grown": lambda i, j: j >= 7},
    "ceo_office":   {"cal": (424, 172), "rw": 12, "rh": 10, "grown": lambda i, j: i >= 10 or j >= 8},
    "meeting_room": {"cal": (423, 173), "rw": 20, "rh": 12, "grown": lambda i, j: i >= 16},
}
BAND = 19.2


def to_px(cal, u, v):
    return ((u - v) * 32 + cal[0], (u + v) * 16 + cal[1])


def back(cal, X, Y):
    a = (X - cal[0]) / 32.0
    b = (Y - cal[1]) / 16.0
    return ((a + b) / 2, (b - a) / 2)


def is_brick(r, g, b, a):
    return a >= 40 and r > g >= b - 8 and r - b > 16


def wall_scan(w, h, px, cal, axis, along_max):
    """Per 0.25-tile along the wall: top edge y, face brick coverage."""
    out = []
    a = 0.0
    while a <= along_max - 0.01:
        fx = 32 * a + cal[0] if axis == "u" else cal[0] - 32 * a
        xi = int(fx) + (6 if axis == "u" else -6)
        base_y = 16 * a + cal[1]
        top = None
        cover = 0
        tot = 0
        for s in range(6, 170):
            y = int(base_y) - s
            if not (0 <= xi < w and 0 <= y < h):
                break
            r, g, b, al = px[y][xi]
            if al >= 40:
                if top is None:
                    top = base_y - s
                tot += 1
                cover += is_brick(r, g, b, al)
        if top is not None:
            out.append((a, top, cover / max(1, tot)))
        a += 0.25
    return out


def fit_wall(scan, name):
    """Robust linear fit of top(a); report fit + broken sub-spans."""
    pts = [(a, t) for (a, t, c) in scan if c > 0.3]
    if len(pts) < 6:
        print(f"  {name}: too little wall to fit ({len(pts)} pts)")
        return None
    for _ in range(4):
        n = len(pts)
        sx = sum(p[0] for p in pts)
        sy = sum(p[1] for p in pts)
        sxx = sum(p[0] * p[0] for p in pts)
        sxy = sum(p[0] * p[1] for p in pts)
        d = n * sxx - sx * sx
        if d == 0:
            break
        c1 = (n * sxy - sx * sy) / d
        c0 = (sy - c1 * sx) / n
        res = [(a, t - (c0 + c1 * a)) for (a, t) in pts]
        keep = [p for p, r in zip(pts, res) if abs(r[1]) <= 4]
        if len(keep) == len(pts):
            break
        pts = keep
    intact_lo = min(p[0] for p in pts)
    intact_hi = max(p[0] for p in pts)
    print(f"  {name}: top(a) = {c0:.1f} {c1:+.2f}a   intact [{intact_lo:.2f}, {intact_hi:.2f}] "
          f"({len(pts)}/{len(scan)} cols)")
    # broken = points outside fit or with low brick coverage / gaps
    broken = []
    for (a, t, c) in scan:
        pred = c0 + c1 * a
        bad = abs(t - pred) > 7 or c < 0.55
        if bad:
            if broken and a - broken[-1][1] <= 0.3:
                broken[-1][1] = a
            else:
                broken.append([a, a])
    if broken:
        spans = ", ".join(f"[{lo:.2f},{hi:.2f}]" for lo, hi in broken)
        print(f"    broken spans: {spans}")
    else:
        print("    broken spans: none")
    # brick coverage strip (clean clone sources have ~1.0)
    strip = ""
    for (a, t, c) in scan:
        if abs(a - round(a)) < 0.01:
            strip += f"{a:4.0f}:{c:.2f}  "
    print(f"    brick coverage: {strip}")
    return (c0, c1, intact_lo, intact_hi)


def tile_junk(w, h, px, cal, i, j):
    """(void_px, mean, sd) over the tile diamond center."""
    vals = []
    void = 0
    for iy in range(2, 16):
        for ix in range(2, 16):
            X, Y = to_px(cal, i + 0.04 + 0.066 * ix, j + 0.04 + 0.066 * iy)
            xi, yi = int(X), int(Y)
            if not (0 <= xi < w and 0 <= yi < h):
                continue
            r, g, b, al = px[yi][xi]
            if al < 40:
                void += 1
                continue
            vals.append((r * 3 + g * 6 + b) // 10)
    if not vals:
        return (196, 0, 0)
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return (void, m, sd)


def main() -> int:
    for rid, cfg in ROOMS.items():
        w, h, px = read_png(ASSETS / f"{rid}.png")
        cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
        print(f"\n===== {rid} {w}x{h} cal={cal} {rw}x{rh} =====")
        print(" -- NE wall (v=0) --")
        scan = wall_scan(w, h, px, cal, "u", rw)
        fit_wall(scan, "NE")
        print(" -- NW wall (u=0) --")
        scan = wall_scan(w, h, px, cal, "v", rh)
        fit_wall(scan, "NW")
        # floor: junk tiles in grown bands + donor candidates (interior)
        junk = []
        clean = []
        for j in range(rh):
            row = ""
            for i in range(rw):
                void, m, sd = tile_junk(w, h, px, cal, i, j)
                if cfg["grown"](i, j):
                    if void > 6 or sd > 24:
                        junk.append((i, j))
                        row += "X"
                    elif void > 0 or sd > 15:
                        row += "x"
                    else:
                        row += "."
                        if len(clean) < 24:
                            clean.append((i, j, m, sd))
                else:
                    row += " "
            print(f"   floor j={j:2d} {row}")
        print(f"   junk tiles ({len(junk)}): {junk}")
        print(f"   grown clean clones (donor candidates): "
              + ", ".join(f"({i},{j})={m:.0f}/{sd:.0f}" for i, j, m, sd in clean[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
