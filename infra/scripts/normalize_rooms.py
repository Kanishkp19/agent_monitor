#!/usr/bin/env python
"""Normalize room art to the canonical 64x32 isometric projection.

    python infra/scripts/normalize_rooms.py

The AI-rendered room PNGs were drawn with per-room tile projections
(measured tile heights 40-49px instead of 32), so no constant offset can
align the tile grid — nav, seats and footprints all drift.

Approach (deterministic, no search):
1. Seed a floor-color palette from the room's SOUTH tip area (always open
   floor in this art set) using the current calibration as a prior.
2. Mask floor-colored pixels, keep the largest connected component.
3. Measure the diamond tips: W (min x), E (max x), S (max y).
4. Solve the exact affine image->world mapping those three points onto
   the canonical diamond corners W/E/S (vertex lattice V(i,j) =
   iso(i,j) + (0,-16); N=(ox,oy) E=(ox+rw,oy) S=(ox+rw,oy+rh) W=(ox,oy+rh)).
5. Invert the affine and resample into a canvas aligned to world axes.

Reads originals from rooms_original/ when present (never double-warps),
writes normalized PNGs into rooms/, prints new CALIBRATION values.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_furniture import ROOMS, read_png, write_png, iso_xy, ASSETS

TW, TH = 64, 32
WALL_MARGIN = 156   # canvas margin above the floor for wall art (meeting room walls are tall)
FLOOR_MARGIN = 36   # below
SEED_RADIUS = 100   # palette sampling radius around the S-tip prior


def vertex(i: float, j: float) -> tuple[float, float]:
    """Floor vertex lattice: top corner of the tile diamond at iso(i,j)."""
    x, y = iso_xy(i, j)
    return (x, y - TH / 2)


def canonical_corners(room) -> dict[str, tuple[float, float]]:
    ox, oy = room["o"]
    rw, rh = room["s"]
    return {
        "N": vertex(ox, oy),
        "E": vertex(ox + rw, oy),
        "S": vertex(ox + rw, oy + rh),
        "W": vertex(ox, oy + rh),
    }


def seed_palette(px, w, h, sx: float, sy: float) -> list[tuple[int, int, int]]:
    """Floor colors from a disc around the image-space S tip prior."""
    buckets: dict[tuple[int, int, int], int] = {}
    r0, r1 = int(sy) - SEED_RADIUS, int(sy) + 10
    c0, c1 = int(sx) - SEED_RADIUS, int(sx) + SEED_RADIUS
    n = 0
    for y in range(max(0, r0), min(h, r1)):
        for x in range(max(0, c0), min(w, c1)):
            r, g, b, a = px[y][x]
            if a < 200:
                continue
            buckets[(r // 12, g // 12, b // 12)] = buckets.get((r // 12, g // 12, b // 12), 0) + 1
            n += 1
    out: list[tuple[int, int, int]] = []
    covered = 0
    for (r, g, b), cnt in sorted(buckets.items(), key=lambda kv: -kv[1]):
        out.append((r * 12 + 6, g * 12 + 6, b * 12 + 6))
        covered += cnt
        if covered >= n * 0.85 or len(out) >= 24:
            break
    return out


def in_palette(c: tuple[int, int, int], pal, tol: int) -> bool:
    r, g, b = c
    return any(
        abs(r - p[0]) <= tol and abs(g - p[1]) <= tol and abs(b - p[2]) <= tol
        for p in pal
    )


def floor_component(px, w, h, pal) -> list[tuple[int, int]]:
    """Largest connected component of floor-colored pixels (4-neighbour)."""
    def is_floor(x: int, y: int) -> bool:
        r, g, b, a = px[y][x]
        return a >= 200 and in_palette((r, g, b), pal, 22)

    seen = [[False] * w for _ in range(h)]
    best: list[tuple[int, int]] = []
    for y0 in range(0, h, 4):
        for x0 in range(0, w, 4):
            if seen[y0][x0] or not is_floor(x0, y0):
                continue
            comp: list[tuple[int, int]] = []
            q = deque([(x0, y0)])
            seen[y0][x0] = True
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and is_floor(nx, ny):
                        seen[ny][nx] = True
                        q.append((nx, ny))
            if len(comp) > len(best):
                best = comp
    return best


def tips(comp: list[tuple[int, int]]) -> dict[str, tuple[float, float]] | None:
    if len(comp) < 2000:
        return None
    minx = min(p[0] for p in comp)
    maxx = max(p[0] for p in comp)
    maxy = max(p[1] for p in comp)
    wpts = [p for p in comp if p[0] <= minx + 2]
    epts = [p for p in comp if p[0] >= maxx - 2]
    spts = [p for p in comp if p[1] >= maxy - 2]
    return {
        "W": (minx, sum(p[1] for p in wpts) / len(wpts)),
        "E": (maxx, sum(p[1] for p in epts) / len(epts)),
        "S": (sum(p[0] for p in spts) / len(spts), maxy),
    }


def solve_affine(src: list[tuple[float, float]], dst: list[tuple[float, float]]):
    """Affine X = A*u+B*v+C, Y = D*u+E*v+F mapping src->dst (3 points)."""
    (u1, v1), (u2, v2), (u3, v3) = src
    (x1, y1), (x2, y2), (x3, y3) = dst
    det = (u1 - u2) * (v1 - v3) - (u1 - u3) * (v1 - v2)
    if abs(det) < 1e-6:
        return None
    # Solve per-axis via Cramer's rule on the 3x3 system.
    def solve_axis(targets: tuple[float, float, float]) -> tuple[float, float, float]:
        t1, t2, t3 = targets
        a = ((t1 - t2) * (v1 - v3) - (t1 - t3) * (v1 - v2)) / det
        b = ((u1 - u2) * (t1 - t3) - (u1 - u3) * (t1 - t2)) / det
        c = t1 - a * u1 - b * v1
        return (a, b, c)
    A, B, C = solve_axis((x1, x2, x3))
    D, E, F = solve_axis((y1, y2, y3))
    return (A, B, C, D, E, F)


def invert_affine(m):
    A, B, C, D, E, F = m
    det = A * E - B * D
    if abs(det) < 1e-9:
        return None
    ia, ib = E / det, -B / det
    id_, ie = -D / det, A / det
    # [ia ib; id ie] @ [[A B],[D E]] = I ; translation: -M^-1 @ (C,F)
    ic = -(ia * C + ib * F)
    if_ = -(id_ * C + ie * F)
    return (ia, ib, ic, id_, ie, if_)


def warp(px, w, h, world_to_img, out_w, out_h, ox0, oy0):
    """Resample: canvas (cx,cy) = world (ox0+cx, oy0+cy) -> image."""
    a, b, c, d, e, f = world_to_img
    out = [[(0, 0, 0, 0)] * out_w for _ in range(out_h)]

    def sample(ix: float, iy: float):
        x0, y0 = int(ix), int(iy)
        fx, fy = ix - x0, iy - y0
        r = g = b2 = a2 = tot = 0.0
        for yy, wy in ((y0, 1 - fy), (y0 + 1, fy)):
            for xx, wx in ((x0, 1 - fx), (x0 + 1, fx)):
                if 0 <= xx < w and 0 <= yy < h:
                    pr, pg, pb, pa = px[yy][xx]
                    wt = wx * wy
                    r += pr * wt; g += pg * wt; b2 += pb * wt; a2 += pa * wt
                    tot += wt
        if tot == 0:
            return (0, 0, 0, 0)
        return (
            int(min(255, r / tot)), int(min(255, g / tot)),
            int(min(255, b2 / tot)), int(min(255, a2 / tot)),
        )

    for cy in range(out_h):
        wy = oy0 + cy
        row = out[cy]
        for cx in range(out_w):
            wx = ox0 + cx
            row[cx] = sample(a * wx + b * wy + c, d * wx + e * wy + f)
    return out


def main() -> int:
    src_dir = ASSETS.parent / "rooms_original"
    if not src_dir.exists():
        src_dir = ASSETS
    print(f"// source: {src_dir}")

    print("// NEW CALIBRATION (paste into WorldRenderer + extract_furniture):")
    for room_id, room in ROOMS.items():
        img_w, img_h, px = read_png(src_dir / f"{room_id}.png")
        can = canonical_corners(room)

        # S-tip prior from the current calibration (image = world - cal offset):
        # image pt for world W:  px = W.x - iso(o).x + cal.dx  (renderer inverse)
        ox, oy = room["o"]
        cal = room["cal"]
        o_iso = iso_xy(ox, oy)
        prior_s = (can["S"][0] - o_iso[0] + cal[0], can["S"][1] - o_iso[1] + cal[1])

        pal = seed_palette(px, img_w, img_h, *prior_s)
        comp = floor_component(px, img_w, img_h, pal)
        t = tips(comp)
        if t is None:
            print(f"  {room_id}: FAILED (floor component too small: {len(comp)} px, palette {len(pal)})")
            continue

        m = solve_affine([t["W"], t["E"], t["S"]], [can["W"], can["E"], can["S"]])
        if m is None:
            print(f"  {room_id}: FAILED (degenerate affine)")
            continue
        inv = invert_affine(m)
        if inv is None:
            print(f"  {room_id}: FAILED (singular affine)")
            continue

        # implied tile size check
        wspan = t["E"][0] - t["W"][0]
        implied_tw = wspan / (room["s"][0] + room["s"][1]) * 2
        implied_th = (t["S"][1] - (t["W"][1] + t["E"][1]) / 2) / ((room["s"][0] + room["s"][1]) / 2)

        xs = [can[k][0] for k in can]
        ys = [can[k][1] for k in can]
        ox0 = int(min(xs)) - 40
        oy0 = int(min(ys)) - WALL_MARGIN
        out_w = int(max(xs) - min(xs)) + 80
        out_h = int(max(ys) - min(ys)) + WALL_MARGIN + FLOOR_MARGIN

        warped = warp(px, img_w, img_h, inv, out_w, out_h, ox0, oy0)
        write_png(ASSETS / f"{room_id}.png", out_w, out_h, warped)

        base_x, base_y = iso_xy(ox, oy)
        ndx = int(round(base_x - ox0))
        ndy = int(round(base_y - oy0))
        print(
            f"  {room_id}: {len(comp)} floor px, implied tile {implied_tw:.1f}x{implied_th:.1f}"
            f" -> canvas {out_w}x{out_h}"
        )
        print(f"    CALIBRATION {room_id}: {{ dx: {ndx}, dy: {ndy} }}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
