#!/usr/bin/env python
"""Repair the shipped devops room art (floor + walls) in place.

    python infra/scripts/repair_devops.py [--check]

The 10x8 -> 12x11 growth pass cloned chevron-walkway / office-chair donor
tiles into the grown bands (rows 8-10, cols 10-11), shredded the NE wall
past u~9.6 (notch + orphan sliver + floating brick fragment east of the
room) and the NW wall from v~7.7 west (hole + detached chunk).

Measured geometry of the shipped art (fits every intact column within 1px):
  NE face (v=0 plane): height H(u) = 5.5u + 10.5 px, band x in [32u, 32u+19.2]
  NW face (u=0 plane): height H(v) = 8.0v + 9.0 px, band x in [32v'-19.2, 32v']
  base lines on the lattice diagonals through CAL=(487,172).

Repairs, in order (floor -> walls -> junk -> end faces -> plinth):

  1. FLOOR: every grown-band tile outside the prop KEEP zone is repainted
     from a verified-clean sandy donor (97%-floorish quad test, probes:
     col-8 strip + row-7 tiles), scattered deterministically, feathered,
     with a shadow gradient on the wall-adjacent strip. Interior tiles are
     original art and never touched.
  2. WALLS: damaged spans are rebuilt per art column: erase junk above the
     measured top edge; clone the intact wall (NE: u-5.45, NW: v-3.45 --
     offsets chosen to skip window and lamp) at the same height above the
     base so brick coursing aligns; synthesize the top band (brick rows
     base-anchored + cap) that has no intact counterpart.
  3. JUNK: pixels beyond the silhouette / east-west of the wall ends erased.
  4. END FACES: the wall slabs are closed at u=12 / v=11 with shaded
     parallelograms following the 9.6px/tile base slant.
  5. PLINTH: canonical rim + slab + shadow below the front edges.

--check verifies only and exits non-zero on failure. The png is written
only when verify passes; a debug copy goes to .freebuff/scratch otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, write_png  # noqa: E402

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
CAL = (487, 172)
RW, RH = 12, 11
TW_HALF, TH_HALF = 32, 16
ROW_H = 62.0 / 7.0          # canonical brick row height (IsoMath wall recipe)
BAND = 19.2                  # wall face band width (0.6 tile)


def to_px(u: float, v: float) -> tuple[float, float]:
    return ((u - v) * TW_HALF + CAL[0], (u + v) * TH_HALF + CAL[1])


def back(X: float, Y: float) -> tuple[float, float]:
    a = (X - CAL[0]) / TW_HALF
    b = (Y - CAL[1]) / TH_HALF
    return ((a + b) / 2, (b - a) / 2)


def edge_y(x: float) -> float:
    x_N, y_N = CAL
    Wx, Wy = x_N - RH * 32, y_N + RH * 16
    Sx, Sy = x_N + (RW - RH) * 32, y_N + (RW + RH) * 16
    if x <= Sx:
        return Wy + 0.5 * (x - Wx)
    return Sy - 0.5 * (x - Sx)


# ── floor ─────────────────────────────────────────────────────────────

# prop rects in the GROWN bands only (interior is never touched)
KEEP: list[tuple[int, int, int, int]] = [
    (10, 3, 10, 5),   # exec cabinet reaches into the east band
]

# verified-clean sandy donors (97%-floorish dense quad test)
DONORS = [(8, 4), (8, 5), (8, 6), (7, 6), (3, 7), (4, 7), (8, 3), (3, 6)]


def in_keep(i: int, j: int) -> bool:
    return any(x0 <= i <= x1 and y0 <= j <= y1 for (x0, y0, x1, y1) in KEEP)


def is_grown(i: int, j: int) -> bool:
    return i >= 10 or j >= 8


def clone_tile(px, w: int, h: int, i: int, j: int, si: int, sj: int) -> int:
    """Copy the donor tile's full diamond onto (i,j) by inverse mapping:
    every pixel whose lattice coords fall in [i,i+1)x[j,j+1) is written
    (a sparse point grid leaves 2px gaps of junk between samples).
    Shadow gradient on wall-adjacent strips (row 0 / col 0)."""
    changed = 0
    ax, ay = to_px(i, j)  # top vertex of the diamond
    for y in range(max(0, int(ay)), min(h, int(ay) + 33)):
        for x in range(max(0, int(ax) - 33), min(w, int(ax) + 34)):
            u, v = back(x + 0.5, y + 0.5)
            fu, fv = u - i, v - j
            if not (0.0 <= fu < 1.0 and 0.0 <= fv < 1.0):
                continue
            dark = 1.0
            if j == 0:
                dark = 0.74 + 0.26 * min(1.0, fv / 0.45)
            elif i == 0:
                dark = 0.74 + 0.26 * min(1.0, fu / 0.45)
            Sx, Sy = to_px(si + fu, sj + fv)
            sxi, syi = int(Sx), int(Sy)
            if not (0 <= sxi < w and 0 <= syi < h):
                continue
            sr, sg, sb, sa = px[syi][sxi]
            if sa < 200:
                continue
            px[y][x] = (int(sr * dark), int(sg * dark), int(sb * dark), 255)
            changed += 1
    return changed


def repair_floor(w: int, h: int, px) -> list[str]:
    notes: list[str] = []
    for j in range(RH):
        for i in range(RW):
            if not is_grown(i, j) or in_keep(i, j):
                continue
            si, sj = DONORS[(i * 7 + j * 5) % len(DONORS)]
            n = clone_tile(px, w, h, i, j, si, sj)
            notes.append(f"floor: ({i:2d},{j:2d}) <- ({si},{sj}) [{n}px]")
    return notes


# ── walls ─────────────────────────────────────────────────────────────

# (name, axis, lo, hi, H(along), x_of(along), src_shift, palette_span)
#   src_shift: intact clone source is at along - src_shift (base-anchored:
#   a pixel s px above the target base maps to s px above the source base).
#   palette_span: (a0, a1) intact, prop-free span for tone sampling.
WALLS = [
    ("NE", "u", 9.55, 12.05, lambda a: 5.5 * a + 10.5,
     lambda a: 32 * a + CAL[0], 5.45, (7.9, 9.2)),
    ("NW", "v", 7.65, 11.05, lambda a: 8.0 * a + 9.0,
     lambda a: CAL[0] - 32 * a, 6.95, (2.2, 3.8)),
]


def sample_palette(px, w: int, h: int, wall) -> dict:
    _, axis, lo, hi, h_at, x_of, _shift, (pa0, pa1) = wall
    face: list[tuple[int, int, int, int]] = []  # (lum, r, g, b)
    caps: list[tuple[int, int, int]] = []
    bases: list[tuple[int, int, int]] = []
    a = pa0
    while a <= pa1:
        H = h_at(a)
        bx, by = int(x_of(a)), int(16 * a + CAL[1])
        for s in range(8, max(12, int(H) - 8)):
            y = by - s
            if 0 <= bx < w and 0 <= y < h:
                r, g, b, al = px[y][bx]
                if al >= 200:
                    face.append(((r * 3 + g * 6 + b) // 10, r, g, b))
        for s in range(int(H) - 5, int(H) - 1):
            y = by - s
            if 0 <= bx < w and 0 <= y < h:
                r, g, b, al = px[y][bx]
                if al >= 200:
                    caps.append((r, g, b))
        for s in range(1, 3):
            y = by - s
            if 0 <= bx < w and 0 <= y < h:
                r, g, b, al = px[y][bx]
                if al >= 200:
                    bases.append((r, g, b))
        a += 0.2

    lums = sorted(f[0] for f in face)
    med = lums[len(lums) // 2] if lums else 120
    face = [f for f in face if f[0] <= med + 40]  # drop lamp/window glow

    def avg(cs, fb):
        if not cs:
            return fb
        n = len(cs)
        return (sum(c[0] for c in cs) // n, sum(c[1] for c in cs) // n, sum(c[2] for c in cs) // n)

    face.sort()
    n5 = max(1, len(face) // 5)
    qs = [face[i * n5:(i + 1) * n5] for i in range(5)]
    tones = [avg([(r, g, b) for _, r, g, b in q], (150, 96, 70)) for q in qs]
    return {"tones": tones, "cap": avg(caps, tones[-1]), "base": avg(bases, tones[0])}


def synth_brick(along: float, s: float, pal: dict):
    """Base-anchored canonical brick row color (62px/7 rows, running bond)."""
    row = int(max(0.0, s) / ROW_H)
    frac = max(0.0, s) - row * ROW_H
    if frac < 0.13:
        return pal["tones"][0]
    ph = (2 * along + 0.5 * row) % 1.0
    if ph < 0.08:
        return pal["tones"][0]
    return pal["tones"][1 + (int(4 * along) * 3 + row * 5) % 4]


def repair_walls(w: int, h: int, px) -> list[str]:
    notes: list[str] = []
    for wall in WALLS:
        name, axis, lo, hi, h_at, x_of, shift, _ps = wall
        pal = sample_palette(px, w, h, wall)
        x0 = int(x_of(lo)) - 2
        x1 = int(x_of(hi)) + int(BAND) + 2
        if axis == "v":
            x0, x1 = int(x_of(hi)) - int(BAND) - 2, int(x_of(lo)) + 2
        painted = erased = 0
        for x in range(max(0, x0), min(w, x1 + 1)):
            a = (x - CAL[0]) / 32.0 if axis == "u" else (CAL[0] - x) / 32.0
            if not (lo <= a <= hi):
                continue
            H = h_at(a)
            yb = 16 * a + CAL[1]
            top_y = yb - H
            for y in range(max(0, int(top_y) - 48), max(0, int(top_y) - 1)):
                if px[y][x][3] > 0:
                    px[y][x] = (0, 0, 0, 0)
                    erased += 1
            asrc = a - shift
            Hs = h_at(asrc)
            for y in range(max(0, int(top_y)), min(h, int(yb) + 4)):
                s = yb - y
                if s >= H - 1.5:
                    c = pal["tones"][0]                    # top edge line
                elif s >= H - 5:
                    c = pal["cap"]                          # cap band
                elif s >= Hs - 6:
                    c = synth_brick(a, s, pal)              # no intact source here
                else:
                    sx = int(x_of(asrc))
                    sy = int(16 * asrc + CAL[1] - s)        # base-anchored clone
                    c = None
                    if 0 <= sx < w and 0 <= sy < h:
                        r, g, b, al = px[sy][sx]
                        if al >= 200 and r - b > 12 and r > g:  # brick-family guard
                            c = (r, g, b)
                            if (r * 3 + g * 6 + b) // 10 > (pal["cap"][0] * 3 + pal["cap"][1] * 6 + pal["cap"][2]) // 10 + 22:
                                c = synth_brick(a, s, pal)  # lamp/window leak guard
                    if c is None:
                        c = synth_brick(a, s, pal)
                if s < -3:
                    continue                                # floor zone below
                px[y][x] = (*c, 255)
                painted += 1
        notes.append(f"{name} wall [{axis} {lo}-{hi}]: {painted}px painted, {erased}px erased, "
                     f"mid tone {pal['tones'][2]}")
    return notes


def draw_end_faces(w: int, h: int, px, pals: dict) -> list[str]:
    """Close the wall slabs at the E/W corners (9.6px/tile base slant)."""
    notes: list[str] = []
    specs = [
        ("NE", 32 * 12 + CAL[0], CAL[1] + 16 * 12, 5.5 * 12 + 10.5, +1, pals["NE"]),
        ("NW", CAL[0] - 32 * 11, CAL[1] + 16 * 11, 8.0 * 11 + 9.0, -1, pals["NW"]),
    ]
    for (name, xe, ye, H, side, pal) in specs:
        n = 0
        for k in range(0, int(BAND) + 1):
            x = xe + side * k
            t = k / BAND
            yb = ye - side * 9.6 * t          # base rises toward the back
            if side < 0:
                yb = ye + 9.6 * t
            for y in range(max(0, int(yb - H) - 1), min(h, int(yb) + 3)):
                s = yb - y
                if s < 2.5:
                    c = pal["base"]
                elif s >= H - 5:
                    c = pal["cap"]
                else:
                    c = tuple(int(v * 0.84) for v in pal["tones"][2])
                if 0 <= x < w:
                    px[y][x] = (*c, 255)
                    n += 1
        notes.append(f"{name} end face: {n}px")
    return notes


# ── junk ──────────────────────────────────────────────────────────────

def erase_junk(w: int, h: int, px) -> list[str]:
    n = 0
    # beyond the floor silhouette (E of u=12, S of v=11)
    for y in range(h):
        for x in range(w):
            if px[y][x][3] < 40:
                continue
            u, v = back(x + 0.5, y + 0.5)
            if u > RW + 0.06 or v > RH + 0.06:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    # floating fragments E/W of the wall end faces
    ye = CAL[1] + 16 * 12
    for y in range(max(0, ye - 130), min(h, ye + 2)):
        for x in range(32 * 12 + CAL[0] + int(BAND) + 1, w):
            if px[y][x][3] > 0:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    # chevron junk WEST of the NW wall face (u < -0.65, below the wall-top
    # headroom); the face itself lives at u in [v-0.6, v], end faces at
    # u in [-0.6, 0], so nothing legit is west of -0.65
    yw = CAL[1] + 16 * 11
    for y in range(max(0, yw - 130), min(h, yw + 2)):
        for x in range(0, max(0, CAL[0] - 32 * 11 - int(BAND))):
            if px[y][x][3] <= 0:
                continue
            y_base = (CAL[0] - x) / 2.0 + CAL[1]
            if y > y_base - 110:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    return [f"junk: erased {n}px"]


# ── plinth ────────────────────────────────────────────────────────────

def redraw_plinth(w: int, h: int, px, rim_h=8, slab_h=22) -> list[str]:
    x_N, y_N = CAL
    Wx, Wy = x_N - RH * 32, y_N + RH * 16
    Sx, Sy = x_N + (RW - RH) * 32, y_N + (RW + RH) * 16
    Ex, Ey = x_N + RW * 32, y_N + RW * 16

    rim_s: list[tuple[int, int, int]] = []
    slab_s: list[tuple[int, int, int]] = []
    for (xa, xb) in ((Wx, Sx), (Sx, Ex)):
        for t in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
            x = int(xa + t * (xb - xa))
            ey = int(edge_y(x))
            for dy, bucket in ((3, rim_s), (10, slab_s), (16, slab_s), (20, slab_s)):
                y = ey + dy
                if 0 <= y < h and px[y][x][3] >= 200:
                    bucket.append(px[y][x][:3])

    def median(cs, fb):
        if not cs:
            return fb
        ch = list(zip(*cs))
        nn = len(ch[0])
        return tuple(sorted(c)[nn // 2] for c in ch)

    rim = median(rim_s, (168, 148, 116))
    slab = median(slab_s, (26, 32, 46))

    n = 0
    for x in range(max(0, int(Wx)), min(w, int(Ex) + 1)):
        ey = int(edge_y(x))
        for y in range(ey, h):
            if y < ey + rim_h:
                px[y][x] = (*rim, 255)
            elif y < ey + rim_h + slab_h - 2:
                px[y][x] = (*slab, 255)
            elif y < ey + rim_h + slab_h:
                px[y][x] = (int(slab[0] * 0.7), int(slab[1] * 0.7), int(slab[2] * 0.7), 255)
            else:
                px[y][x] = (0, 0, 0, 0)
            n += 1
    for x in range(0, min(w, max(0, int(Wx)))):
        for y in range(max(0, int(Wy)), h):
            if px[y][x][3] != 0:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    for x in range(int(Ex) + 1, w):
        for y in range(max(0, int(Ey)), h):
            if px[y][x][3] != 0:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    return [f"plinth: repainted {n}px (rim {rim}, slab {slab})"]


# ── verify ────────────────────────────────────────────────────────────

def tile_stats(w: int, h: int, px, i: int, j: int):
    vals = []
    for iy in range(4, 14):
        for ix in range(4, 14):
            X, Y = to_px(i + 0.06 + 0.058 * ix, j + 0.06 + 0.058 * iy)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] >= 200:
                vals.append((px[yi][xi][0] * 3 + px[yi][xi][1] * 6 + px[yi][xi][2]) // 10)
    if not vals:
        return None
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return m, sd


def is_bricky(r: int, g: int, b: int, a: int) -> bool:
    if a < 40:
        return False
    return r > g >= b - 8 and r - b > 16


def verify(w: int, h: int, px) -> list[str]:
    errs: list[str] = []
    # repainted floor tiles must match their donors
    for j in range(RH):
        for i in range(RW):
            if not is_grown(i, j) or in_keep(i, j):
                continue
            si, sj = DONORS[(i * 7 + j * 5) % len(DONORS)]
            tgt = tile_stats(w, h, px, i, j)
            don = tile_stats(w, h, px, si, sj)
            if not tgt or not don:
                errs.append(f"tile ({i},{j}): no opaque samples")
                continue
            if abs(tgt[0] - don[0]) > 16 or abs(tgt[1] - don[1]) > 11:
                errs.append(f"tile ({i},{j}) mean/sd {tgt[0]:.0f}/{tgt[1]:.0f} "
                            f"vs donor {don[0]:.0f}/{don[1]:.0f}")

    # wall faces: brick ratio, no void, nothing above the top edge
    for wall in WALLS:
        name, axis, lo, hi, h_at, x_of, _sx, _sp = wall
        tot = hit = void = above = 0
        a = lo + 0.1
        while a <= hi - 0.1:
            H = h_at(a)
            bx, by = int(x_of(a)) + (6 if axis == "u" else -6), int(16 * a + CAL[1])
            for s in range(8, min(56, int(H) - 8), 3):
                y = by - s
                if 0 <= bx < w and 0 <= y < h:
                    r, g, b, al = px[y][bx]
                    tot += 1
                    if al < 40:
                        void += 1
                    else:
                        hit += is_bricky(r, g, b, al)
            for y in range(max(0, int(by - H) - 42), max(0, int(by - H) - 1)):
                if 0 <= bx < w and px[y][bx][3] >= 40:
                    above += 1
            a += 0.2
        if tot:
            if hit / tot < 0.85:
                errs.append(f"{name} wall only {hit * 100 // max(1, tot)}% brick-family")
            if void / tot > 0.02:
                errs.append(f"{name} wall {void * 100 // tot}% void in core band")
        if above:
            errs.append(f"{name} wall: {above}px junk above the top edge")

    # end faces present
    for (name, xs, ys, ye) in (("NE", 32 * 12 + CAL[0] + 9, 280, 362),
                               ("NW", CAL[0] - 32 * 11 - 9, 258, 344)):
        op = sum(1 for y in range(ys, ye) if px[y][xs][3] >= 200)
        if op < (ye - ys) * 0.9:
            errs.append(f"{name} end face incomplete ({op}/{ye - ys})")

    # nothing opaque E/W of the end faces
    ye = CAL[1] + 16 * 12
    out_e = sum(1 for y in range(max(0, ye - 130), min(h, ye + 1))
                for x in range(32 * 12 + CAL[0] + int(BAND) + 1, w) if px[y][x][3] > 0)
    yw = CAL[1] + 16 * 11
    out_w = sum(1 for y in range(max(0, yw - 130), min(h, yw + 1))
                for x in range(0, max(0, CAL[0] - 32 * 11 - int(BAND))) if px[y][x][3] > 0)
    if out_e or out_w:
        errs.append(f"junk outside end faces (E {out_e}px, W {out_w}px)")
    return errs


# ── main ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify only; exit 1 on failure")
    ap.add_argument("--no-save", action="store_true", help="run repairs, never write the shipped png")
    args = ap.parse_args()

    w, h, px = read_png(SHIP)
    print(f"repairing {SHIP.name} ({w}x{h})")

    notes: list[str] = []
    if not args.check:
        backup = SHIP.with_suffix(".orig.png")
        if not backup.exists():
            write_png(backup, w, h, px)
            print(f"  backup: {backup.name}")
        notes += repair_floor(w, h, px)
        pals = {wall[0]: sample_palette(px, w, h, wall) for wall in WALLS}
        notes += repair_walls(w, h, px)
        notes += erase_junk(w, h, px)
        notes += draw_end_faces(w, h, px, pals)
        notes += redraw_plinth(w, h, px)
        for n in notes:
            print(" ", n)

    errs = verify(w, h, px)
    if errs:
        print("VERIFY: FAIL")
        for e in errs:
            print("  -", e)
        code = 1
    else:
        print("VERIFY: OK")
        code = 0

    if not args.check and code == 0 and not args.no_save:
        write_png(SHIP, w, h, px)
        print(f"wrote {SHIP}")
    elif not args.check:
        dbg = ROOT / ".freebuff" / "scratch" / "devops_debug.png"
        dbg.parent.mkdir(parents=True, exist_ok=True)
        write_png(dbg, w, h, px)
        print(f"debug copy at {dbg}" + ("" if code == 0 else " (verify FAILED, not saved)"))
    return code


if __name__ == "__main__":
    sys.exit(main())
