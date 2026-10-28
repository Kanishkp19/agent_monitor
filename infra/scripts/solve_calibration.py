#!/usr/bin/env python
"""Solve exact room calibration from the floor diamond in the art.

    python infra/scripts/solve_calibration.py

The floor diamond's four extreme corners in image space map to known
world-space tile corners:

    topmost floor point    = corner of tile (0,0)      (north corner)
    leftmost floor point   = corner of tile (0, h-1)   (west corner)
    rightmost floor point  = corner of tile (w-1, 0)   (east corner)
    bottommost floor point = corner of tile (w-1, h-1) (south corner)

Given iso() and the room origin o, each corner's world position is known;
the detected image position yields calibration (dx, dy) directly:
    imageX = worldX - baseX + dx   →   dx = imageX - worldX + baseX

We detect floor pixels with an adaptive palette (sampled from the front
band), take the extremes of the largest floor region, and print the solved
offsets next to the current ones. These offsets go into WorldRenderer
CALIBRATION and extract_furniture ROOMS — one geometry, everywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_furniture import (
    ROOMS,
    read_png,
    sample_floor_palette,
    iso_xy,
    ASSETS,
)


def solve(room_id: str) -> dict:
    room = ROOMS[room_id]
    ox, oy = room["o"]
    w, h = room["s"]
    img_w, img_h, px = read_png(ASSETS / f"{room_id}.png")

    floor = sample_floor_palette(px, img_w, img_h, room)
    base_floor = list(floor)
    for k in (0.85, 0.7, 0.55, 0.45):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base_floor]

    def is_floor(x: int, y: int) -> bool:
        r, g, b, a = px[y][x]
        if a < 200:
            return False
        return any(
            abs(r - p[0]) <= 20 and abs(g - p[1]) <= 20 and abs(b - p[2]) <= 20
            for p in floor
        )

    # Largest connected floor region (BFS, 4-neighbor). This excludes
    # look-alikes: dark TV panels, rugs, window glass — none of which
    # connect to the actual tile floor.
    seen = bytearray(img_w * img_h)
    best: list[tuple[int, int]] = []
    for y0 in range(img_h):
        for x0 in range(img_w):
            idx0 = y0 * img_w + x0
            if seen[idx0] or not is_floor(x0, y0):
                continue
            stack = [(x0, y0)]
            seen[idx0] = 1
            comp: list[tuple[int, int]] = []
            while stack:
                x, y = stack.pop()
                comp.append((x, y))
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < img_w and 0 <= ny < img_h:
                        nidx = ny * img_w + nx
                        if not seen[nidx] and is_floor(nx, ny):
                            seen[nidx] = 1
                            stack.append((nx, ny))
            if len(comp) > len(best):
                best = comp
    if len(best) < 500:
        return {}

    # Extremes of the floor region (diamond corners), using per-row lists.
    rows_with_floor: dict[int, list[int]] = {}
    for x, y in best:
        rows_with_floor.setdefault(y, []).append(x)
    ordered = sorted(rows_with_floor.items())

    top_y, top_xs = ordered[0]
    bot_y, bot_xs = ordered[-1]
    left_x = min(min(xs) for _, xs in ordered)
    right_x = max(max(xs) for _, xs in ordered)

    # Corner image points. Occlusion-aware: the front three corners
    # (south tip, west tip, east tip) are on open floor in all five rooms;
    # the north corner is usually behind furniture, so it is reported but
    # only trusted when it agrees.
    top_pt = (sum(top_xs) / len(top_xs), float(top_y))
    bot_pt = (sum(bot_xs) / len(bot_xs), float(bot_y))
    left_pt = (float(left_x), None)
    right_pt = (float(right_x), None)
    for y, xs in ordered:
        if min(xs) == left_x:
            left_pt = (float(left_x), float(y))
        if max(xs) == right_x:
            right_pt = (float(right_x), float(y))

    base_x, base_y = iso_xy(ox, oy)

    # World positions of the diamond corners:
    #   north = top vertex of tile (0,0)      → iso(ox, oy) - (0, 16)
    #   south = bottom vertex of tile (w-1,h-1) → iso corner + (0, +16)
    #   west  = left vertex of tile (0,h-1)   → iso + (-32, +16 relative)
    #   east  = right vertex of tile (w-1,0)  → iso + (+32, +16 relative)
    # iso(a,b) gives the TOP vertex of that tile's diamond; the left/right
    # vertices sit at ±32px x and +16px y from it; the bottom at +32px y.
    w_top = (iso_xy(ox, oy)[0], iso_xy(ox, oy)[1] - 16)
    w_bot = (iso_xy(ox + w - 1, oy + h - 1)[0], iso_xy(ox + w - 1, oy + h - 1)[1] + 32 - 16 + 16)
    # bottom vertex of the south tile = its top vertex + (0, 32)
    w_bot = (iso_xy(ox + w - 1, oy + h - 1)[0], iso_xy(ox + w - 1, oy + h - 1)[1] + 32)
    w_left = (iso_xy(ox, oy + h - 1)[0] - 32, iso_xy(ox, oy + h - 1)[1] + 16)
    w_right = (iso_xy(ox + w - 1, oy)[0] + 32, iso_xy(ox + w - 1, oy)[1] + 16)

    per_corner = {
        "N": (top_pt, w_top),
        "S": (bot_pt, w_bot),
        "W": (left_pt, w_left),
        "E": (right_pt, w_right),
    }

    estimates: dict[str, tuple[float, float]] = {}
    for k, (img_pt, w_pt) in per_corner.items():
        ix, iy = img_pt
        wx, wy = w_pt
        estimates[k] = (ix - wx + base_x, iy - wy + base_y)

    # Trust S, W, E (front corners); N only for reporting.
    trusted = [estimates[k] for k in ("S", "W", "E")]
    dx = sorted(e[0] for e in trusted)[1]  # median
    dy = sorted(e[1] for e in trusted)[1]
    spread = max(
        max(e[0] for e in trusted) - min(e[0] for e in trusted),
        max(e[1] for e in trusted) - min(e[1] for e in trusted),
    )
    return {
        "dx": round(dx), "dy": round(dy), "spread": round(spread, 1),
        "per_corner": {k: (round(v[0]), round(v[1])) for k, v in estimates.items()},
    }


def main() -> int:
    print("// solved calibration (compare with WorldRenderer CALIBRATION):")
    for room_id in ROOMS:
        cur = ROOMS[room_id]["cal"]
        got = solve(room_id)
        if not got:
            print(f"  {room_id}: FAILED")
            continue
        pc = got.get("per_corner", {})
        pcs = " ".join(f"{k}=({v[0]},{v[1]})" for k, v in pc.items())
        print(
            f"  {room_id}: solved dx={got['dx']} dy={got['dy']} "
            f"(spread {got['spread']}px) — current dx={cur[0]} dy={cur[1]} "
            f"Δ=({got['dx'] - cur[0]}, {got['dy'] - cur[1]})   corners: {pcs}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
