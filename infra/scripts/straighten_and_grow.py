#!/usr/bin/env python
"""Grow the archived room art to the symmetric building layout.

    python infra/scripts/straighten_and_grow.py

Reads the archived art (infra/rooms_v1/), writes office/rooms/<id>.png.
Idempotent: always starts from the archive.

Measurement first: the archive art's floor diamond is ALREADY on the
canonical 64x32 lattice — its silhouette matches the nominal N/W/S/E
corners and the shipped footprints were validated against it. What
looks like "tilt" in the silhouettes is the decorative SLAB SIDE under
the floor, drawn shallower than the floor by design in every room.
Earlier attempts to "straighten" it sheared the rooms (the user saw
exactly that distortion), so this script never warps pixels.

What it does instead — zero-distortion growth to TARGET sizes:

1. GROW EAST/SOUTH in whole-tile bands on the lattice: new floor is
   cloned from open-floor donor tiles (nav-map driven), rim/wall bands
   translate along the lattice axes. The warp is lattice-locked, so the
   user-approved footprints stay valid without re-extraction.
2. REDRAW the below-floor slab canonically: the AI art draws the base
   under each room at random depths/slopes (0.37-0.49 instead of +-0.5,
   6-101px deep) — that is the visible "tilt" and the dark wings. The
   redraw erases everything below the front floor polyline and paints a
   uniform plinth (the room's own rim tone + a flat slab) so all rooms
   share one crisp building silhouette.
3. VERIFY what ships: zero transparent samples on the floor plane and
   the S rim tip at the nominal lattice spot (+ the constant drop).
4. Print the CALIBRATION entries (archive cal + growth shift) to paste
   into WorldRenderer / calibrate.ts / extract_furniture.py.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_furniture import (
    read_png,
    write_png,
    ASSETS,
    sample_floor_palette,
    tile_center_px,
    wall_region_tester,
    near,
    BG,
)

# Archive art geometry (infra/rooms_v1/).
SOURCE: dict[str, dict] = {
    "dev_floor":    {"s": (20, 20), "cal": (680, 173)},
    "managers":     {"s": (12, 7),  "cal": (264, 172)},
    "ceo_office":   {"s": (10, 8),  "cal": (296, 172)},
    "devops":       {"s": (10, 8),  "cal": (295, 172)},
    "meeting_room": {"s": (16, 12), "cal": (423, 173)},
}

# Target sizes (the symmetric 32x32 building, right column 12 wide).
TARGET: dict[str, tuple[int, int]] = {
    "dev_floor": (20, 20),
    "managers": (12, 11),
    "ceo_office": (12, 10),
    "devops": (12, 11),
    "meeting_room": (20, 12),
}

ARC_DIR = Path(__file__).resolve().parents[1] / "rooms_v1"
TW_HALF, TH_HALF = 32, 16
EDGE = math.hypot(TW_HALF, TH_HALF)  # px per tile along a floor edge
TIP_TOL_PX = 16


def to_px(u: float, v: float, cal) -> tuple[float, float]:
    return ((u - v) * TW_HALF + cal[0], (u + v) * TH_HALF + cal[1])


def back(X: float, Y: float, cal) -> tuple[float, float]:
    a = (X - cal[0]) / TW_HALF
    b = (Y - cal[1]) / TH_HALF
    return ((a + b) / 2, (b - a) / 2)


# ── rim outline from the void bottom envelope (verification signal) ───


def bottom_envelope(px, w, h):
    env: dict[int, int] = {}
    for x in range(0, w, 2):
        for y in range(h - 1, -1, -1):
            r, g, b, a = px[y][x]
            if a >= 40 and not (
                abs(r - BG[0]) < 14 and abs(g - BG[1]) < 14 and abs(b - BG[2]) < 14
            ):
                env[x] = y
                break
    return env


def sample(px, w, h, x: float, y: float):
    """Bilinear sample; outside the canvas is transparent."""
    x0, y0 = int(math.floor(x)), int(math.floor(y))
    fx, fy = x - x0, y - y0
    r = g = b = a = tot = 0.0
    for yy, wy in ((y0, 1 - fy), (y0 + 1, fy)):
        for xx, wx in ((x0, 1 - fx), (x0 + 1, fx)):
            if 0 <= xx < w and 0 <= yy < h:
                pr, pg, pb, pa = px[yy][xx]
                wt = wx * wy
                r += pr * wt
                g += pg * wt
                b += pb * wt
                a += pa * wt
                tot += wt
    if tot == 0:
        return (0, 0, 0, 0)
    return (int(r / tot), int(g / tot), int(b / tot), int(a / tot))


def heal_pinholes(px, w, h):
    """Fill fully-transparent pixels surrounded by opaque neighbours.

    The AI art carries 1-2px alpha pinholes inside the floor; at render
    scale they show the page background. Interior-only fill (>=3 opaque
    4-neighbours), so the true void outside the diamond is untouched.
    Returns the number of healed pixels.
    """
    holes = []
    for y in range(h):
        for x in range(w):
            if px[y][x][3] >= 40:
                continue
            nb = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < w and 0 <= yy < h and px[yy][xx][3] >= 40:
                    nb += 1
            if nb >= 3:
                holes.append((x, y))
    for x, y in holes:
        r = g = b = n = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            xx, yy = x + dx, y + dy
            if 0 <= xx < w and 0 <= yy < h and px[yy][xx][3] >= 40:
                pr, pg, pb, _ = px[yy][xx]
                r += pr
                g += pg
                b += pb
                n += 1
        if n:
            px[y][x] = (r // n, g // n, b // n, 255)
    return len(holes)


def fill_floor_voids(px, w, h, rw, rh, cal):
    """Fill transparent pixels that lattice-map inside the floor slab.

    The AI art leaves void notches between the floor diamond and the slab
    rim near the S tip (plus pinholes elsewhere). Any transparent pixel
    whose lattice coords fall within [-0.25, rw+0.25] x [-0.25, rh+0.25]
    belongs to the slab — fill it from the nearest opaque neighbours so
    the room silhouette reads solid. Pixels beyond that box are the true
    outside void and stay transparent.
    """
    filled = 0
    for y in range(h):
        for x in range(w):
            if px[y][x][3] >= 40:
                continue
            u, v = back(x + 0.5, y + 0.5, cal)
            if -0.25 <= u <= rw + 0.25 and -0.25 <= v <= rh + 0.25:
                best = None
                for rad in range(1, 15):
                    acc = [0, 0, 0]
                    n = 0
                    for dy in range(-rad, rad + 1):
                        for dx in range(-rad, rad + 1):
                            if max(abs(dx), abs(dy)) != rad:
                                continue
                            xx, yy = x + dx, y + dy
                            if 0 <= xx < w and 0 <= yy < h and px[yy][xx][3] >= 40:
                                p = px[yy][xx]
                                acc[0] += p[0]
                                acc[1] += p[1]
                                acc[2] += p[2]
                                n += 1
                    if n:
                        best = (acc[0] // n, acc[1] // n, acc[2] // n, 255)
                        break
                if best:
                    px[y][x] = best
                    filled += 1
    return filled


def redraw_slab(px, w, h, rw, rh, cal, rim_h=8, slab_h=22):
    """Rebuild the below-floor base as a canonical plinth.

    The archive art's decorative slab hangs below the floor at random
    depths and slopes per room (measured 0.37-0.49 faces, 6-101px deep,
    plus a stray staircase wing) — the user-visible "uneven tilt". This
    pass erases EVERYTHING below the front floor polyline (W->S->E,
    extended flat beyond the tips) and repaints a uniform plinth:

      rows  edge_y      .. edge_y+rim_h        rim band (room's own tone)
      rows  edge_y+rim_h.. edge_y+rim_h+slab_h flat slab face (sampled)

    Rim/slab colors are sampled from the existing art per face before the
    erase, with sane fallbacks, so each room keeps its character while
    the base geometry becomes exactly +-0.5 — the building silhouette.
    """
    x_N, y_N = cal
    Wx, Wy = x_N - rh * 32, y_N + rh * 16
    Sx, Sy = x_N + (rw - rh) * 32, y_N + (rw + rh) * 16
    Ex, Ey = x_N + rw * 32, y_N + rw * 16

    def edge_y(x: float) -> float:
        if x <= Sx:
            return Wy + 0.5 * (x - Wx)
        return Sy - 0.5 * (x - Sx)

    # -- sample rim + slab colors from the existing art (before erase) --
    def median(colors):
        if not colors:
            return None
        ch = list(zip(*colors))
        n = len(ch[0])
        return tuple(sorted(c)[n // 2] for c in ch)

    rim_s: dict[str, list] = {"sw": [], "se": []}
    slab_s: dict[str, list] = {"sw": [], "se": []}
    for face, (xa, xb) in (("sw", (Wx, Sx)), ("se", (Sx, Ex))):
        for t in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9):
            x = int(xa + t * (xb - xa))
            ey = int(edge_y(x))
            for dy, bucket in ((3, rim_s), (10, slab_s), (16, slab_s), (20, slab_s)):
                y = ey + dy
                if 0 <= y < h and px[y][x][3] >= 200:
                    bucket[face].append(px[y][x][:3])
    FALLBACK_RIM = (168, 148, 116)
    FALLBACK_SLAB = (26, 32, 46)
    rim = {f: median(rim_s[f]) or FALLBACK_RIM for f in rim_s}
    slab = {f: median(slab_s[f]) or FALLBACK_SLAB for f in slab_s}

    # -- make room for the plinth --
    need = max(int(edge_y(x)) for x in range(int(Wx), int(Ex) + 1)) + rim_h + slab_h + 2
    if need > h:
        for _ in range(need - h):
            px.append([(0, 0, 0, 0)] * w)
        h = need

    # -- erase below-floor content, paint the canonical plinth --
    for x in range(max(0, int(Wx)), min(w, int(Ex) + 1)):
        ey = int(edge_y(x))
        face = "sw" if x <= Sx else "se"
        for y in range(ey, h):
            if y < ey + rim_h:
                px[y][x] = (*rim[face], 255)
            elif y < ey + rim_h + slab_h - 2:
                px[y][x] = (*slab[face], 255)
            elif y < ey + rim_h + slab_h:
                c = slab[face]
                px[y][x] = (int(c[0] * 0.7), int(c[1] * 0.7), int(c[2] * 0.7), 255)
            else:
                px[y][x] = (0, 0, 0, 0)
    # beyond the tips: everything below the corner levels is void (kills
    # the stray wings/staircase the art painted outside the diamond)
    for x in range(0, min(w, max(0, int(Wx)))):
        for y in range(max(0, int(Wy)), h):
            px[y][x] = (0, 0, 0, 0)
    for x in range(int(Ex) + 1, w):
        for y in range(max(0, int(Ey)), h):
            px[y][x] = (0, 0, 0, 0)
    return px, w, h


def devegetate_band(px, w, h, rw, rh, cal, bands, floor_pal):
    """Replace non-floor pixels inside the grown bands with floor color.

    Donor tiles inevitably carry some prop pixels (canopies, pot edges,
    shadows of things out of frame); rather than chase every source,
    sweep the grown band rects and repaint anything that isn't the floor
    palette (incl. its shading) with the nearest passing pixel. Voids are
    left alone (none should exist inside the floor).
    """
    floor = list(floor_pal)
    base = list(floor_pal)
    for k in (0.85, 0.7, 0.55, 0.4):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base]

    def in_band(x, y):
        u, v = back(x + 0.5, y + 0.5, cal)
        return any(u0 <= u <= u1 and v0 <= v <= v1 for (u0, v0, u1, v1) in bands)

    fixed = 0
    for y in range(h):
        for x in range(w):
            if px[y][x][3] < 40 or not in_band(x, y):
                continue
            if near(px[y][x][:3], floor, 26):
                continue
            found = None
            for rad in range(1, 26):
                acc = [0, 0, 0]
                n = 0
                for dy in range(-rad, rad + 1):
                    for dx in range(-rad, rad + 1):
                        if max(abs(dx), abs(dy)) != rad:
                            continue
                        xx, yy = x + dx, y + dy
                        if not (0 <= xx < w and 0 <= yy < h):
                            continue
                        q = px[yy][xx]
                        if q[3] >= 40 and near(q[:3], floor, 26):
                            acc[0] += q[0]
                            acc[1] += q[1]
                            acc[2] += q[2]
                            n += 1
                if n:
                    found = (acc[0] // n, acc[1] // n, acc[2] // n, 255)
                    break
            if found:
                px[y][x] = found
                fixed += 1
    return fixed


def verify(px, w, h, rw, rh, cal):
    """Void samples inside the floor rectangle + S rim tip spot."""
    errs = []
    voids = 0
    steps = 4
    inset = 0.08
    for jv in range(0, rh * steps + 1):
        for iu in range(0, rw * steps + 1):
            u, v = iu / steps, jv / steps
            if not (inset <= u <= rw - inset and inset <= v <= rh - inset):
                continue
            X, Y = to_px(u, v, cal)
            xi, yi = int(X), int(Y)
            if not (0 <= xi < w and 0 <= yi < h):
                errs.append("floor rectangle outside canvas")
                return errs
            if px[yi][xi][3] < 40:
                voids += 1
    if voids > 0:
        errs.append(f"{voids} void samples inside floor rectangle")
    env = bottom_envelope(px, w, h)
    if env:
        Sc = to_px(rw, rh, cal)
        x = min(env, key=lambda k: abs(k - Sc[0]))
        dS = abs(env[x] - Sc[1])
        if dS > TIP_TOL_PX + 24:  # nominal + constant slab drop (~22px)
            errs.append(f"S tip off {dS - 24:.0f}px beyond drop")
    return errs


# ── nav-map helpers for donor selection ────────────────────────────────


def derive_floor_palette(px, w, h, cal, rw, rh, strict):
    """Floor palette from STRICT-clean tiles only (never the S-tip disc).

    The S-tip seed disc lands inside cloned bands on grown art, poisoning
    the palette with plant greens (which then pass as floor forever).
    Strict-clean tiles are pure floor by construction — sample discs
    there instead.
    """
    room = {"o": (0, 0), "s": (rw, rh), "cal": tuple(cal)}
    cand = [(i, j) for j in range(rh) for i in range(rw) if not strict[j][i]]
    if not cand:
        return sample_floor_palette(px, w, h, room)
    ci, cj = rw / 2, rh / 2
    cand.sort(key=lambda c: (c[0] - ci) ** 2 + (c[1] - cj) ** 2)
    buckets: dict[tuple[int, int, int], int] = {}
    for (i, j) in cand[:6]:
        cx, cy = tile_center_px(room, i, j)
        for y in range(max(0, cy - 10), min(h, cy + 10)):
            for x in range(max(0, cx - 10), min(w, cx + 10)):
                r, g, b, a = px[y][x]
                if a < 200:
                    continue
                k = (r // 10, g // 10, b // 10)
                buckets[k] = buckets.get(k, 0) + 1
    out = []
    for (r, g, b), _n in sorted(buckets.items(), key=lambda kv: -kv[1])[:14]:
        out.append((r * 10 + 5, g * 10 + 5, b * 10 + 5))
    return out


def blocked_map(px, w, h, rw, rh, cal, floor_pal=None):
    room = {"o": (0, 0), "s": (rw, rh), "cal": tuple(cal)}
    floor = floor_pal if floor_pal is not None else sample_floor_palette(px, w, h, room)
    base = list(floor)
    for k in (0.85, 0.7, 0.55, 0.45):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base]
    is_wall = wall_region_tester(room)
    DXS = (-20, -10, 0, 10, 20)

    def non_floor(x, y):
        r, g, b, a = px[y][x]
        if a < 40 or is_wall(x, y):
            return False
        if abs(r - BG[0]) < 14 and abs(g - BG[1]) < 14 and abs(b - BG[2]) < 14:
            return False
        return not near((r, g, b), floor, 20)

    def blocked(i, j):
        cx, cy = tile_center_px(room, i, j)
        bh = bt = 0
        for dx in DXS:
            for dy in (-6, -2, 2):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    bt += 1
                    if non_floor(x, y):
                        bh += 1
        if bt > 0 and bh / bt > 0.55:
            return True
        mh = mt = 0
        lum = []
        for dx in DXS:
            for dy in range(-34, -6, 4):
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    mt += 1
                    r, g, b, a = px[y][x]
                    lum.append((r + g + b) // 3)
                    if non_floor(x, y):
                        mh += 1
        spread = (max(lum) - min(lum)) if lum else 0
        return mt > 0 and mh / mt > 0.55 and spread > 18

    return [[blocked(i, j) for i in range(rw)] for j in range(rh)]


def open_at(bl, i, j):
    return 0 <= i < len(bl[0]) and 0 <= j < len(bl) and not bl[j][i]


# sample grid over the WHOLE tile quad (lower diamond + upper body zone).
# Dense by design (~4px spacing): a donor tile is cloned verbatim, so ANY
# prop pixel inside it (plant foliage ~50px wide, pot edge, shadow) must
# disqualify it — sparse grids let plants slip between samples.
DIAMOND_OFFS = [
    (0.04 + 0.073 * ix, 0.04 + 0.073 * iy)
    for iy in range(13)
    for ix in range(13)
]


def modal_tone(means):
    """Per-channel median of tile means — the dominant floor tone.

    Rugs/lounges cover a minority of tiles in every room, so the median
    tile is genuine floor. Donors must match THIS tone, not just the
    local palette (a sandy rug tile can pass a palette test if the
    palette itself was seeded near the rug).
    """
    chans = list(zip(*means.values()))
    n = len(chans[0])
    return tuple(sorted(c)[n // 2] for c in chans)


def strict_open_map(px, w, h, rw, rh, cal, floor_pal=None, modal=None):
    """Tiles whose whole quad (incl. behind-tile canopy chain) is floor.

    Donor candidates for growth: cloning a tile that carries any prop
    (plant, shelf edge, shadowed clutter) repeats that prop across the
    whole grown band — the artifact the user flagged.
    """
    room = {"o": (0, 0), "s": (rw, rh), "cal": tuple(cal)}
    floor = floor_pal if floor_pal is not None else sample_floor_palette(px, w, h, room)
    base = list(floor)
    for k in (0.8, 0.65, 0.5):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base]
    is_wall = wall_region_tester(room)
    clean = [[False] * rw for _ in range(rh)]
    for j in range(rh):
        for i in range(rw):
            good = True
            acc = [0, 0, 0]
            ns = 0
            for du, dv in DIAMOND_OFFS:
                X, Y = to_px(i + du, j + dv, cal)
                xi, yi = int(X), int(Y)
                if not (0 <= xi < w and 0 <= yi < h):
                    good = False
                    break
                if is_wall(xi, yi):
                    continue
                r, g, b, a = px[yi][xi]
                if a < 40 or not near((r, g, b), floor, 20):
                    good = False
                    break
                acc[0] += r
                acc[1] += g
                acc[2] += b
                ns += 1
            if good and modal is not None and ns:
                mean = (acc[0] / ns, acc[1] / ns, acc[2] / ns)
                if sum(abs(mean[k] - modal[k]) for k in range(3)) > 90:
                    good = False  # rug/lounge tone: not clonable floor
            clean[j][i] = good
    # canopy rule: a prop standing at (i+k, j+k) paints its foliage k*32px
    # UP in image space, landing on tile (i, j) — so a tile is clone-safe
    # only if the WHOLE diagonal chain behind it (to the room's S corner)
    # is clean. Propagate from the S corner backwards.
    ok = [[clean[j][i] for i in range(rw)] for j in range(rh)]
    for j in range(rh - 2, -1, -1):
        for i in range(rw - 2, -1, -1):
            if ok[j][i] and not ok[j + 1][i + 1]:
                ok[j][i] = False
    return ok


def tile_means(px, w, h, cal, rw, rh):
    """Mean RGB of each tile's floor quad (tone map for donor matching)."""
    out = {}
    for j in range(rh):
        for i in range(rw):
            acc = [0, 0, 0]
            n = 0
            for du, dv in DIAMOND_OFFS:
                X, Y = to_px(i + du, j + dv, cal)
                xi, yi = int(X), int(Y)
                if 0 <= xi < w and 0 <= yi < h and px[yi][xi][3] >= 40:
                    p = px[yi][xi]
                    acc[0] += p[0]
                    acc[1] += p[1]
                    acc[2] += p[2]
                    n += 1
            out[(i, j)] = (acc[0] / n, acc[1] / n, acc[2] / n) if n else (0, 0, 0)
    return out


def pick_donors(band, strict, bl, means, edge_tone, mode, rw_old, rh_old, modal=None):
    """Donor per band tile: cleanest AND tone-matched to the room edge.

    Same-column donors can clone a rug/lounge area (devops' sandy band),
    so candidates are scored primarily by TONE DISTANCE to the tone of
    the floor line being extended (means is clamped internally), with
    same-column and south-row proximity as tie breakers (keeps the
    vignette direction natural).

    Polarity: bl is True=BLOCKED (candidates `not bl`), strict is
    True=CLEAN (candidates strict itself).
    """
    use_strict = strict is not None and any(any(row) for row in strict)
    rw, rh = len(bl[0]), len(bl)

    def clean(i, j):
        return strict[j][i] if use_strict else not bl[j][i]

    # only tiles in the wall-free southern part of the room: the back wall
    # overhangs the top rows and the wall tester SKIPS those pixels in the
    # clean test, so top-row tiles can carry invisible wall-base fragments
    # (the "HSW" mazes). The south half is proven prop-free by the test.
    jmin = rh // 3
    cands = [(i, j) for j in range(jmin, rh) for i in range(rw) if clean(i, j)]

    def cdist(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])

    def cands_tone(i, j):
        return means[(min(i, rw - 1), min(j, rh - 1))]

    out = {}
    for (di, dj) in band:
        # continue the LOCAL gradient: match the tone of the floor line
        # this band tile extends (clamped into the archive rect)
        tgt = cands_tone(di, dj)
        scored = sorted(
            cands,
            key=lambda c: (
                3 * cdist(means[c], tgt)
                + (0.6 if (mode == 'south' and c[0] == di) or (mode == 'east' and c[1] == dj) else 0)
                + 0.25 * abs(c[1] - (rh_old - 1))
            ),
        )
        out[(di, dj)] = scored[(di + dj) % min(3, len(scored))]
    return out


# ── growth passes (whole-tile bands on the lattice) ───────────────────


def grow_east(px, w, h, rw, rh, cal, dw, bl, strict, floor_pal, means, modal):
    """Extend the room to rw+dw: donor-floor band + translated rim/walls.

    Content stays glued at cal; the canvas grows east/south. cal unchanged.
    bl/strict/floor_pal/means describe the ARCHIVE art (donors live there).
    """
    n_strict = sum(sum(1 for c in row if not c) for row in strict)
    band = [(i, j) for i in range(rw, rw + dw) for j in range(rh)]
    donors = pick_donors(band, strict, bl, means, None, 'east', rw, rh, modal)
    print(f"    grow_east +{dw}: strict-open donors {n_strict}/{rw * rh}")
    w2, h2 = w + 2 * TW_HALF * dw, h + TH_HALF * dw
    out = [[(0, 0, 0, 0)] * w2 for _ in range(h2)]
    rw_new = rw + dw

    def clipj(j):
        return max(0, min(rh - 1, int(j)))

    def src_of(u, v):
        if u < -6.0 or u > rw_new + 0.6 or v < -6.0 or v > rh + 0.6:
            return None
        if v < -0.2:  # NE wall band: preserve; far end translated
            return (u - dw, v) if u > rw else (u, v)
        if u >= rw_new - 1e-6:  # new SE rim face: old rim translated
            return (u - dw, v)
        if v > rh:  # SW rim strip extension
            return (u - dw, v) if u > rw else (u, v)
        if u >= rw:  # new floor band -> donor tile (lattice-aligned)
            j0 = clipj(v)
            iu = min(int(u), rw_new - 1)
            di, dj = donors[(iu, j0)]
            return (u - (iu - di), v - (j0 - dj))
        return (u, v)

    for Y in range(h2):
        row = out[Y]
        for X in range(w2):
            u, v = back(X, Y, cal)
            s = src_of(u, v)
            row[X] = (0, 0, 0, 0) if s is None else sample(px, w, h, *to_px(s[0], s[1], cal))
    return out, w2, h2, cal


def grow_south(px, w, h, rw, rh, cal, dh, bl, strict, floor_pal, means, modal):
    """Extend the room to rh+dh: donor-floor band + translated rim/walls.

    Content shifts east by 2*TW*dh in the grown canvas (which also grows
    east/south); cal2 = cal + 2*TW*dh keeps the world placement.
    bl/strict/floor_pal/means describe the ARCHIVE art (donors live there).
    """
    n_strict = sum(sum(1 for c in row if not c) for row in strict)
    band = [(i, j) for j in range(rh, rh + dh) for i in range(rw)]
    donors = pick_donors(band, strict, bl, means, None, 'south', rw, rh, modal)
    print(f"    grow_south +{dh}: strict-open donors {n_strict}/{rw * rh}")
    cal2 = (cal[0] + 2 * TW_HALF * dh, cal[1])
    w2, h2 = w + 2 * TW_HALF * dh, h + TH_HALF * dh
    out = [[(0, 0, 0, 0)] * w2 for _ in range(h2)]
    rh_new = rh + dh

    def clipi(i):
        return max(0, min(rw - 1, int(i)))

    def src_of(u, v):
        if u < -6.0 or u > rw + 0.6 or v < -6.0 or v > rh_new + 0.6:
            return None
        if u < -0.2:  # NW wall band: preserve; far end translated
            return (u, v - dh) if v > rh else (u, v)
        if v >= rh_new - 1e-6:  # new SW rim face: old rim translated
            return (u, v - dh)
        if u > rw:  # SE rim strip extension
            return (u, v - dh) if v > rh else (u, v)
        if v >= rh:  # new floor band -> donor tile (lattice-aligned)
            i0 = clipi(u)
            jv = min(int(v), rh_new - 1)
            di, dj = donors[(i0, jv)]
            return (u - (i0 - di), v - (jv - dj))
        return (u, v)

    for Y in range(h2):
        row = out[Y]
        for X in range(w2):
            u, v = back(X, Y, cal2)
            s = src_of(u, v)
            # sample the SOURCE in its own frame (cal), never cal2
            row[X] = (0, 0, 0, 0) if s is None else sample(px, w, h, *to_px(s[0], s[1], cal))
    return out, w2, h2, cal2


# ── main ───────────────────────────────────────────────────────────────


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    ARC_DIR.mkdir(parents=True, exist_ok=True)
    print("// grow to symmetric building (archive art, zero distortion)")
    for rid, src in SOURCE.items():
        rw_old, rh_old = src["s"]
        rw_new, rh_new = TARGET[rid]
        cal = tuple(src["cal"])
        w, h, px = read_png(ARC_DIR / f"{rid}.png")

        dw, dh = rw_new - rw_old, rh_new - rh_old
        # donor maps + floor palette come from the ARCHIVE art, once
        means = tile_means(px, w, h, cal, rw_old, rh_old)
        modal = modal_tone(means)
        strict = strict_open_map(px, w, h, rw_old, rh_old, cal, modal=modal)
        fpal = derive_floor_palette(px, w, h, cal, rw_old, rh_old, strict)
        bl = blocked_map(px, w, h, rw_old, rh_old, cal)

        if dw > 0:
            px, w, h, cal = grow_east(px, w, h, rw_old, rh_old, cal, dw, bl, strict, fpal, means, modal)
        if dh > 0:
            px, w, h, cal = grow_south(px, w, h, rw_new, rh_old, cal, dh, bl, strict, fpal, means, modal)

        # canonical plinth: uniform rim+slab base on the exact +-0.5 faces
        px, w, h = redraw_slab(px, w, h, rw_new, rh_new, cal)

        # de-vegetate the grown bands (donor prop leftovers)
        bands = []
        if dh > 0:
            bands.append((0.0, float(rh_old), float(rw_new), float(rh_new)))
        if dw > 0:
            bands.append((float(rw_old), 0.0, float(rw_new), float(rh_old)))
        deveg = 0  # dense-clean donors make repainting unnecessary (it flattened tone)

        healed = fill_floor_voids(px, w, h, rw_new, rh_new, cal)
        healed += heal_pinholes(px, w, h)
        errs = verify(px, w, h, rw_new, rh_new, cal)
        status = "OK" if not errs else f"CHECK ({'; '.join(errs)})"
        print(f"  {rid}: {rw_old}x{rh_old} -> {rw_new}x{rh_new}  filled {healed}px  deveg {deveg}px  {status}")
        print(f"    CALIBRATION {rid}: {{ dx: {cal[0]:.0f}, dy: {cal[1]:.0f} }}  // canvas {w}x{h}")

        write_png(ASSETS / f"{rid}.png", w, h, px)
    return 0


if __name__ == "__main__":
    sys.exit(main())
