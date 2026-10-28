#!/usr/bin/env python
"""Repair the three remaining grown rooms: managers, ceo_office, meeting_room.

    python infra/scripts/repair_rooms.py [room ...] [--check] [--no-save]

Same disease as devops (fixed by repair_devops.py): the 10x8/12x7/16x12 ->
target growth pass cloned chevron/prop donor tiles into the grown floor
bands and shredded the wall spans past the archive edge, leaving holes,
floating fragments and chevron junk. Rooms: managers 12x7->12x11,
ceo_office 10x8->12x10, meeting_room 16x12->20x12.

Measured geometry (top-edge scan, fits every intact column within ~1px):
  managers NE: top_y = 159.1+11.73a  -> H(a) = 12.9+4.27a   (break u>=11.0)
  managers NW: top_y = 157.9+ 6.53v  -> H(v) = 14.1+9.47v   (break v>=7.75)
  ceo     NE: top_y = 162.8+10.42a  -> H(a) =  9.2+5.58a   (break u>=9.5)
  ceo     NW: top_y = 162.9+ 8.05v  -> H(v) =  9.1+7.95v   (break v>=8.25)
  meeting NE: top_y = -14.8+15.98a  -> H(a) =187.8+0.02a   (break u>=14.75)
  meeting NW: intact.

Pipeline per room (floor -> walls -> junk -> end faces -> plinth), then a
geometric verify; the png is written only when verify passes.

  1. FLOOR  every grown-band tile repainted from verified-clean donor tiles
            (full-diamond inverse-mapped clone, deterministic scatter).
  2. WALLS  damaged spans rebuilt per art column: junk above the measured
            top edge erased; intact wall cloned from a prop-free offset
            (base-anchored so coursing aligns); heights past the source's
            own top synthesized canonically; a brick-family guard rejects
            window/lamp leakage into the clone.
  3. JUNK   pixels beyond the silhouette / beside the end faces erased.
  4. FACES  wall slabs closed at u=RW / v=RH with shaded parallelograms.
  5. PLINTH rim + slab redrawn canonically below the front floor edges.

--check verifies the on-disk png only (exit 1 on failure).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, write_png  # noqa: E402

ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"
TW_HALF, TH_HALF = 32, 16
ROW_H = 62.0 / 7.0          # canonical brick row height (IsoMath wall recipe)
BAND = 19.2                  # wall face band width (0.6 tile)

# ── per-room config ───────────────────────────────────────────────────
# walls: (name, axis, lo, hi, H(along), x_of(along), src_shift, palette_span)
#   clone source is at along - src_shift (base-anchored).
ROOM_CFG: dict[str, dict] = {
    "managers": {
        "cal": (520, 172), "rw": 12, "rh": 11,
        "grown": lambda i, j: j >= 7,
        "keep": [],
        "donors": [(4, 8), (5, 8), (5, 7), (4, 9), (4, 10), (3, 7), (6, 8), (3, 10)],
        "walls": [
            ("NE", "u", 10.90, 12.05,
             lambda a: 12.9 + 4.27 * a, lambda a: 32 * a + 520, 4.15, (7.0, 7.8)),
            ("NW", "v", 7.60, 11.05,
             lambda v: 14.1 + 9.47 * v, lambda v: 520 - 32 * v, 7.50, (1.0, 3.0)),
        ],
        "end_faces": ("NE", "NW"),
    },
    "ceo_office": {
        "cal": (424, 172), "rw": 12, "rh": 10,
        "grown": lambda i, j: i >= 10 or j >= 8,
        "keep": [],
        "donors": [(10, 2), (10, 3), (10, 4), (3, 8), (4, 8), (9, 5)],
        "walls": [
            ("NE", "u", 9.40, 12.05,
             lambda a: 9.2 + 5.58 * a, lambda a: 32 * a + 424, 5.50, (4.2, 6.2)),
            ("NW", "v", 8.15, 10.05,
             lambda v: 9.1 + 7.95 * v, lambda v: 424 - 32 * v, 5.00, (3.3, 4.9)),
        ],
        "end_faces": ("NE", "NW"),
    },
    "meeting_room": {
        "cal": (423, 173), "rw": 20, "rh": 12,
        "grown": lambda i, j: i >= 16,
        "keep": [],
        # clean flat blue-gray strip on the archive's east edge
        "donors": [(15, 1), (15, 2), (15, 3), (15, 4), (15, 5),
                   (15, 6), (15, 7), (15, 8), (15, 9), (15, 10)],
        "walls": [
            ("NE", "u", 14.75, 20.05,
             lambda a: 187.8 + 0.02 * a, lambda a: 32 * a + 423, 5.50, (9.7, 10.9)),
        ],
        "end_faces": ("NE",),   # NW wall + its end face are intact
        "west_face_h": 187.0,   # measured: meeting walls are ~187px tall
    },
}


def make_geo(cal, rw, rh):
    def to_px(u: float, v: float) -> tuple[float, float]:
        return ((u - v) * TW_HALF + cal[0], (u + v) * TH_HALF + cal[1])

    def back(X: float, Y: float) -> tuple[float, float]:
        a = (X - cal[0]) / TW_HALF
        b = (Y - cal[1]) / TH_HALF
        return ((a + b) / 2, (b - a) / 2)

    def edge_y(x: float) -> float:
        x_N, y_N = cal
        Wx, Wy = x_N - rh * 32, y_N + rh * 16
        Sx, Sy = x_N + (rw - rh) * 32, y_N + (rw + rh) * 16
        if x <= Sx:
            return Wy + 0.5 * (x - Wx)
        return Sy - 0.5 * (x - Sx)

    return to_px, back, edge_y


# ── floor ─────────────────────────────────────────────────────────────

def in_keep(cfg, i: int, j: int) -> bool:
    return any(x0 <= i <= x1 and y0 <= j <= y1
               for (x0, y0, x1, y1) in cfg["keep"])


def clone_tile(px, w, h, to_px, back, i, j, si, sj) -> int:
    """Copy the donor tile's full diamond onto (i,j) by inverse mapping.
    Shadow gradient on wall-adjacent strips (row 0 / col 0)."""
    changed = 0
    ax, ay = to_px(i, j)
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


def repair_floor(cfg, w, h, px, to_px, back) -> list[str]:
    notes: list[str] = []
    don = cfg["donors"]
    for j in range(cfg["rh"]):
        for i in range(cfg["rw"]):
            if not cfg["grown"](i, j) or in_keep(cfg, i, j):
                continue
            si, sj = don[(i * 7 + j * 5) % len(don)]
            n = clone_tile(px, w, h, to_px, back, i, j, si, sj)
            notes.append(f"floor: ({i:2d},{j:2d}) <- ({si},{sj}) [{n}px]")
    return notes


# ── walls ─────────────────────────────────────────────────────────────

def sample_palette(px, w, h, cal, wall) -> dict:
    _, axis, _lo, _hi, h_at, x_of, _shift, (pa0, pa1) = wall
    face: list[tuple[int, int, int, int]] = []
    caps: list[tuple[int, int, int]] = []
    bases: list[tuple[int, int, int]] = []
    a = pa0
    while a <= pa1:
        H = h_at(a)
        bx, by = int(x_of(a)), int(16 * a + cal[1])
        for s in range(8, max(12, int(H) - 8)):
            y = by - s
            if 0 <= bx < w and 0 <= y < h:
                r, g, b, al = px[y][bx]
                if al >= 200:
                    face.append(((r * 3 + g * 6 + b) // 10, r, g, b))
        for s in range(max(6, int(H) - 5), int(H) - 1):
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
        return (sum(c[0] for c in cs) // n, sum(c[1] for c in cs) // n,
                sum(c[2] for c in cs) // n)

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


def repair_walls(cfg, w, h, px) -> list[str]:
    cal = cfg["cal"]
    notes: list[str] = []
    for wall in cfg["walls"]:
        name, axis, lo, hi, h_at, x_of, shift, _ps = wall
        pal = sample_palette(px, w, h, cal, wall)
        x0 = int(x_of(lo)) - 2
        x1 = int(x_of(hi)) + int(BAND) + 2
        if axis == "v":
            x0, x1 = int(x_of(hi)) - int(BAND) - 2, int(x_of(lo)) + 2
        painted = erased = 0
        for x in range(max(0, x0), min(w, x1 + 1)):
            a = (x - cal[0]) / 32.0 if axis == "u" else (cal[0] - x) / 32.0
            if not (lo <= a <= hi):
                continue
            H = h_at(a)
            yb = 16 * a + cal[1]
            top_y = yb - H
            for y in range(max(0, int(top_y) - 175), max(0, int(top_y) - 1)):
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
                    sy = int(16 * asrc + cal[1] - s)        # base-anchored clone
                    c = None
                    if 0 <= sx < w and 0 <= sy < h:
                        r, g, b, al = px[sy][sx]
                        if al >= 200 and r - b > 12 and r > g:  # brick guard
                            c = (r, g, b)
                            lum = (r * 3 + g * 6 + b) // 10
                            cap_lum = (pal["cap"][0] * 3 + pal["cap"][1] * 6
                                       + pal["cap"][2]) // 10
                            if lum > cap_lum + 22:
                                c = synth_brick(a, s, pal)  # window/lamp leak
                    if c is None:
                        c = synth_brick(a, s, pal)
                if s < -3:
                    continue                                # floor zone below
                px[y][x] = (*c, 255)
                painted += 1
        notes.append(f"{name} wall [{axis} {lo}-{hi}]: {painted}px painted, "
                     f"{erased}px erased, mid tone {pal['tones'][2]}")
    return notes


def draw_end_faces(cfg, w, h, px, pals) -> list[str]:
    """Close the wall slabs at the E/W corners (9.6px/tile base slant)."""
    cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
    by_name = {wall[0]: wall for wall in cfg["walls"]}
    notes: list[str] = []
    for name in cfg["end_faces"]:
        side = +1 if name == "NE" else -1
        along = rw if name == "NE" else rh
        wall = by_name[name]
        xe = (32 * rw + cal[0]) if name == "NE" else (cal[0] - 32 * rh)
        ye = cal[1] + 16 * (rw if name == "NE" else rh)
        H = wall[4](along)
        pal = pals[name]
        n = 0
        for k in range(0, int(BAND) + 1):
            x = xe + side * k
            t = k / BAND
            # both end faces RISE toward the outer corner (the outer corner
            # sits at thickness -0.6, i.e. 9.6px higher on screen)
            yb = ye - 9.6 * t
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

def erase_junk(cfg, w, h, px, back) -> list[str]:
    cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
    n = 0
    # beyond the floor silhouette (E of u=RW, S of v=RH)
    for y in range(h):
        for x in range(w):
            if px[y][x][3] < 40:
                continue
            u, v = back(x + 0.5, y + 0.5)
            if u > rw + 0.06 or v > rh + 0.06:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    # floating fragments E/W of the wall end faces
    ye = cal[1] + 16 * rw
    for y in range(max(0, ye - 175), min(h, ye + 2)):
        for x in range(32 * rw + cal[0] + int(BAND) + 1, w):
            if px[y][x][3] > 0:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    # junk WEST of the NW wall face (u < -0.65). Two rules: the per-pixel
    # headroom cut, plus a flat cut from the wall's west-end top (the art
    # lets the wall tip lean up to ~40px past the canonical corner; the
    # drawn end face replaces it).
    yw = cal[1] + 16 * rh
    xe_w = cal[0] - 32 * rh
    h_nw = next((wl[4](rh) for wl in cfg["walls"] if wl[0] == "NW"), None)
    if h_nw is None:
        h_nw = cfg.get("west_face_h", 16.0 * rh)
    y_flat = yw - h_nw - 9.6 - 40
    for y in range(max(0, min(yw - 175, int(y_flat))), min(h, yw + 2)):
        for x in range(0, max(0, int(xe_w) - int(BAND))):
            if px[y][x][3] <= 0:
                continue
            y_base = (cal[0] - x) / 2.0 + cal[1]
            if y > y_base - 175 or y > y_flat:
                px[y][x] = (0, 0, 0, 0)
                n += 1
    return [f"junk: erased {n}px"]


# ── plinth ────────────────────────────────────────────────────────────

def redraw_plinth(cfg, w, h, px, edge_y, rim_h=8, slab_h=22) -> list[str]:
    cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
    x_N, y_N = cal
    Wx, Wy = x_N - rh * 32, y_N + rh * 16
    Sx, Sy = x_N + (rw - rh) * 32, y_N + (rw + rh) * 16
    Ex, Ey = x_N + rw * 32, y_N + rw * 16

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
                px[y][x] = (int(slab[0] * 0.7), int(slab[1] * 0.7),
                            int(slab[2] * 0.7), 255)
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

def tile_stats(w, h, px, to_px, i: int, j: int):
    vals = []
    for iy in range(4, 14):
        for ix in range(4, 14):
            X, Y = to_px(i + 0.06 + 0.058 * ix, j + 0.06 + 0.058 * iy)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] >= 200:
                vals.append((px[yi][xi][0] * 3 + px[yi][xi][1] * 6
                             + px[yi][xi][2]) // 10)
    if not vals:
        return None
    m = sum(vals) / len(vals)
    sd = (sum((v - m) ** 2 for v in vals) / len(vals)) ** 0.5
    return m, sd


def is_bricky(r: int, g: int, b: int, a: int) -> bool:
    if a < 40:
        return False
    return r > g >= b - 8 and r - b > 16


def verify(cfg, w, h, px, to_px, back) -> list[str]:
    errs: list[str] = []
    cal, rw, rh = cfg["cal"], cfg["rw"], cfg["rh"]
    don = cfg["donors"]

    # repainted floor tiles must match their donors
    for j in range(rh):
        for i in range(rw):
            if not cfg["grown"](i, j) or in_keep(cfg, i, j):
                continue
            si, sj = don[(i * 7 + j * 5) % len(don)]
            tgt = tile_stats(w, h, px, to_px, i, j)
            d = tile_stats(w, h, px, to_px, si, sj)
            if not tgt or not d:
                errs.append(f"tile ({i},{j}): no opaque samples")
                continue
            if abs(tgt[0] - d[0]) > 16 or abs(tgt[1] - d[1]) > 11:
                errs.append(f"tile ({i},{j}) mean/sd {tgt[0]:.0f}/{tgt[1]:.0f} "
                            f"vs donor {d[0]:.0f}/{d[1]:.0f}")

    # wall faces: brick ratio, no void, nothing above the top edge
    for wall in cfg["walls"]:
        name, axis, lo, hi, h_at, x_of, _sx, _sp = wall
        tot = hit = void = above = 0
        a = lo + 0.1
        while a <= hi - 0.1:
            H = h_at(a)
            bx, by = int(x_of(a)) + (6 if axis == "u" else -6), int(16 * a + cal[1])
            for s in range(8, min(56, int(H) - 8), 3):
                y = by - s
                if 0 <= bx < w and 0 <= y < h:
                    r, g, b, al = px[y][bx]
                    tot += 1
                    if al < 40:
                        void += 1
                    else:
                        hit += is_bricky(r, g, b, al)
            for y in range(max(0, int(by - H) - 60), max(0, int(by - H) - 1)):
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

    # end faces present (span derived from each wall's own height + 9.6 rise)
    for name in cfg["end_faces"]:
        wall = next(wl for wl in cfg["walls"] if wl[0] == name)
        along = rw if name == "NE" else rh
        H = wall[4](along)
        xe = (32 * rw + cal[0]) if name == "NE" else (cal[0] - 32 * rh)
        ye2 = cal[1] + 16 * (rw if name == "NE" else rh)
        xs = int(xe + (9 if name == "NE" else -9))
        ys = int(ye2 - 9.6 - H) - 2
        op = sum(1 for y in range(max(0, ys), min(h, ye2)) if px[y][xs][3] >= 200)
        need = int(H) + 2
        if op < need:
            errs.append(f"{name} end face incomplete ({op}/{need})")

    # nothing opaque E/W of the end faces (west window derived from the
    # wall's west-end top, same as the erase rule)
    ye = cal[1] + 16 * rw
    out_e = sum(1 for y in range(max(0, ye - 175), min(h, ye + 1))
                for x in range(32 * rw + cal[0] + int(BAND) + 1, w) if px[y][x][3] > 0)
    yw = cal[1] + 16 * rh
    h_nw = next((wl[4](rh) for wl in cfg["walls"] if wl[0] == "NW"), None)
    if h_nw is None:
        h_nw = cfg.get("west_face_h", 16.0 * rh)
    y_flat = int(yw - h_nw - 9.6 - 40)
    out_w = sum(1 for y in range(max(0, min(yw - 175, y_flat)), min(h, yw + 1))
                for x in range(0, max(0, cal[0] - 32 * rh - int(BAND))) if px[y][x][3] > 0)
    if out_e or out_w:
        errs.append(f"junk outside end faces (E {out_e}px, W {out_w}px)")
    return errs


# ── main ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rooms", nargs="*", help="rooms to repair (default: all)")
    ap.add_argument("--check", action="store_true", help="verify only; exit 1 on failure")
    ap.add_argument("--no-save", action="store_true", help="run repairs, never write")
    args = ap.parse_args()

    names = args.rooms or list(ROOM_CFG)
    rc = 0
    for rid in names:
        cfg = dict(ROOM_CFG[rid])
        cfg["_id"] = rid
        ship = ASSETS / f"{rid}.png"
        w, h, px = read_png(ship)
        to_px, back, edge_y = make_geo(cfg["cal"], cfg["rw"], cfg["rh"])
        print(f"\n== {rid} {w}x{h} cal={cfg['cal']} {cfg['rw']}x{cfg['rh']} ==")

        if not args.check:
            backup = ship.with_name(f"{rid}.orig.png")
            if not backup.exists():
                write_png(backup, w, h, px)
                print(f"  backup: {backup.name}")
            notes: list[str] = []
            notes += repair_floor(cfg, w, h, px, to_px, back)
            pals = {wall[0]: sample_palette(px, w, h, cfg["cal"], wall)
                    for wall in cfg["walls"]}
            # ensure end faces have a palette even when their wall isn't rebuilt
            for name in cfg["end_faces"]:
                if name not in pals:
                    wall = next((wl for wl in cfg["walls"] if wl[0] == name), None)
                    if wall is None:
                        axis = "u" if name == "NE" else "v"
                        along = cfg["rw"] if name == "NE" else cfg["rh"]
                        wall = (name, axis, along - 1.0, along + 0.05,
                                (lambda aa: 12.9 + 4.27 * aa) if axis == "u"
                                else (lambda vv: 14.1 + 9.47 * vv),
                                (lambda aa: 32 * aa + cfg["cal"][0]) if axis == "u"
                                else (lambda vv: cfg["cal"][0] - 32 * vv),
                                1.0, (1.0, 2.0))
                    pals[name] = sample_palette(px, w, h, cfg["cal"], wall)
            notes += repair_walls(cfg, w, h, px)
            notes += erase_junk(cfg, w, h, px, back)
            notes += draw_end_faces(cfg, w, h, px, pals)
            notes += redraw_plinth(cfg, w, h, px, edge_y)
            for nnote in notes:
                print("  ", nnote)

        errs = verify(cfg, w, h, px, to_px, back)
        if errs:
            print("  VERIFY: FAIL")
            for e in errs:
                print("    -", e)
            rc = 1
        else:
            print("  VERIFY: OK")

        if not args.check:
            if not errs and not args.no_save:
                write_png(ship, w, h, px)
                print(f"  wrote {ship}")
            else:
                dbg = ROOT / ".freebuff" / "scratch" / f"repair_debug_{rid}.png"
                dbg.parent.mkdir(parents=True, exist_ok=True)
                write_png(dbg, w, h, px)
                print(f"  debug copy at {dbg}"
                      + ("" if errs else " (--no-save)"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
