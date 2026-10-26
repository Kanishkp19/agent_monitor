#!/usr/bin/env python
"""Damage + donor map for managers, ceo_office, meeting_room.

Per room: donor-eligible tiles (>=97% floorish quad), void samples inside
the floor rect, non-floorish tiles in the GROWN bands, wall column
intactness (NE face at v=0, NW face at u=0), and canvas extents vs nominal.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))
from extract_furniture import read_png

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"

ROOMS = {
    # id: (rw, rh, cal, size_source)  size_source = (rw,rh) before growth
    "managers":     (12, 11, (520, 172)),
    "ceo_office":   (12, 10, (424, 172)),
    "meeting_room": (20, 12, (423, 173)),
}
GROWN = {"managers": (10, 8), "ceo_office": (10, 8), "meeting_room": (16, 12)}


def to_px(u, v, cal):
    return ((u - v) * 32 + cal[0], (u + v) * 16 + cal[1])


def floorish(r, g, b, a, room):
    if a < 200:
        return False
    lum = (r * 3 + g * 6 + b) // 10
    if room == "meeting_room":
        return (b >= r - 4 and b >= 55) or lum <= 42 or (r - b > 18 and r >= 55)
    return (r - b >= 18 and r >= 55) or (b >= r + 6 and b >= 55) or lum <= 42


for rid, (rw, rh, cal) in ROOMS.items():
    ship = ASSETS / f"{rid}.png"
    w, h, px = read_png(ship)
    grw, grh = GROWN[rid]
    print(f"\n===== {rid}  {w}x{h}  room {rw}x{rh} (grown from {grw}x{grh}) =====")

    # donor eligibility
    elig = [["." for _ in range(rw)] for _ in range(rh)]
    for j in range(rh):
        for i in range(rw):
            tot = ok = 0
            for iy in range(10):
                for ix in range(10):
                    du, dv = 0.08 + 0.09 * ix, 0.08 + 0.09 * iy
                    X, Y = to_px(i + du, j + dv, cal)
                    xi, yi = int(X), int(Y)
                    if not (0 <= xi < w and 0 <= yi < h):
                        continue
                    r, g, b, a = px[yi][xi]
                    tot += 1
                    if floorish(r, g, b, a, rid):
                        ok += 1
            if tot and ok / tot >= 0.97:
                elig[j][i] = "D"
    print("  donor map (D=eligible):")
    for j in range(rh):
        print(f"    {j:2d} " + "".join(elig[j][i] for i in range(rw)))

    # voids inside floor rect (grown bands)
    voids = []
    for j in range(grh, rh):
        for i in range(rw):
            X, Y = to_px(i + 0.5, j + 0.5, cal)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] < 40:
                voids.append((i, j))
    for i in range(grw, rw):
        for j in range(grh):
            X, Y = to_px(i + 0.5, j + 0.5, cal)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] < 40:
                voids.append((i, j))
    print(f"  void tiles in grown bands: {voids if voids else 'none'}")

    # wall column intactness: NE face (v=0), H = 5.5u+10.5; NW face (u=0)
    def col_ok(u_or_v, axis):
        if axis == "u":
            bx, by = to_px(u_or_v, 0.0, cal)
        else:
            bx, by = to_px(0.0, u_or_v, cal)
        if not (0 <= int(bx) < w):
            return False
        H = 5.5 * u_or_v + 10.5 if axis == "u" else 8.0 * u_or_v + 9.0
        # sample band s=6..H-8
        s0, s1 = 6, max(8, int(H) - 8)
        op = br = 0
        for s in range(s0, s1, 2):
            y = int(by - s)
            if not (0 <= y < h):
                continue
            r, g, b, a = px[y][int(bx)]
            if a < 40:
                continue
            op += 1
            if r - b > 12 and r > g:
                br += 1
        return op == 0 or (br / op >= 0.5 and op >= (s1 - s0) // 2 * 0.8)

    ne = [i for i in range(rw) if not col_ok(i + 0.0, "u")]
    nw = [j for j in range(rh) if not col_ok(j + 0.0, "v")]
    print(f"  suspect NE wall columns (u): {ne if ne else 'none'}")
    print(f"  suspect NW wall columns (v): {nw if nw else 'none'}")

    # opaque pixels beyond the silhouette
    out = 0
    for y in range(h):
        for x in range(w):
            if px[y][x][3] < 40:
                continue
            a = (x - cal[0]) / 32.0
            b = (y - cal[1]) / 16.0
            u, v = (a + b) / 2, (b - a) / 2
            if u > rw + 0.06 or v > rh + 0.06:
                out += 1
    print(f"  opaque px beyond silhouette: {out}")
