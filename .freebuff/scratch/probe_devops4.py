#!/usr/bin/env python
"""Probe #4: per-tile diff shipped-vs-archive under the growth mapping.

Mapping (from straighten_and_grow): east band u>=10 <- archive u-2;
south band v>=8 <- archive v-3; interior (u<10, v<8) <- archive same.
For each shipped tile: mean |diff| vs mapped archive tile, plus
cleanliness of both under the CORRECTED floor test (saturation-aware).
Also: histogram of the junk (chair) pixels in the shipped south band.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, near, BG  # noqa: E402

SHIP_P = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms" / "devops.png"
ARC_P = ROOT / "infra" / "rooms_v1" / "devops.png"
SHIP_CAL = (487, 172)
ARC_CAL = (295, 172)
RW, RH = 12, 11
TW_HALF, TH_HALF = 32, 16

FLOOR_CORE = [(105, 85, 76), (126, 109, 94)]


def to_px(u: float, v: float, cal) -> tuple[float, float]:
    return ((u - v) * TW_HALF + cal[0], (u + v) * TH_HALF + cal[1])


def sample_mean(px, w, h, i, j, cal) -> tuple[float, float, float] | None:
    acc = [0.0, 0.0, 0.0]
    n = 0
    for iy in range(14):
        for ix in range(14):
            du = dv = 0.05 + 0.065 * ix
            X, Y = to_px(i + du, j + dv, cal)
            xi, yi = int(X), int(Y)
            if not (0 <= xi < w and 0 <= yi < h):
                return None
            r, g, b, a = px[yi][xi]
            if a < 200:
                return None
            acc[0] += r
            acc[1] += g
            acc[2] += b
            n += 1
    return (acc[0] / n, acc[1] / n, acc[2] / n) if n else None


def corrected_floor(c) -> bool:
    r, g, b = c
    if r - b < 12:
        return False  # kills desaturated chair grays
    shades = []
    for k in (1.0, 0.85, 0.7, 0.55):
        shades += [(int(r0 * k), int(g0 * k), int(b0 * k)) for r0, g0, b0 in FLOOR_CORE]
    return near((r, g, b), shades, 18)


def donor_uv(i: int, j: int) -> tuple[int, int]:
    return (i - 2 if i >= 10 else i, j - 3 if j >= 8 else j)


def main() -> int:
    sw, sh, sp = read_png(SHIP_P)
    aw, ah, ap = read_png(ARC_P)
    print(f"shipped {sw}x{sh}, archive {aw}x{ah}")

    print("\n== per-tile: diff% (shipped vs mapped archive) / shipClean archClean ==")
    print("     " + "".join(f"{i:5d}" for i in range(RW)))
    for j in range(RH):
        cells = []
        for i in range(RW):
            sm = sample_mean(sp, sw, sh, i, j, SHIP_CAL)
            di, dj = donor_uv(i, j)
            am = sample_mean(ap, aw, ah, di, dj, ARC_CAL) if (0 <= di < 10 and 0 <= dj < 8) else None
            if sm is None:
                cells.append("  na ")
                continue
            if am is None:
                cells.append("  -- ")
                continue
            diff = sum(abs(sm[k] - am[k]) for k in range(3)) / 3
            sc = "Y" if corrected_floor(sm) else "n"
            ac = "Y" if corrected_floor(am) else "n"
            cells.append(f"{diff:4.0f}{sc}{ac}")
        print(f"  {j:2d} " + " ".join(cells))

    print("\nlegend: diff = mean |shipped-mappedArchive| per channel; "
          "Y/n = passes corrected floor test")

    # junk histogram: opaque pixels in shipped south band v in [7.5, 10.5]
    from collections import Counter
    buckets: Counter = Counter()
    for y in range(sh):
        for x in range(sw):
            r, g, b, a = sp[y][x]
            if a < 200:
                continue
            aa = (x - SHIP_CAL[0]) / TW_HALF
            bb = (y - SHIP_CAL[1]) / TH_HALF
            u, v = (aa + bb) / 2, (bb - aa) / 2
            if 7.5 <= v <= 10.5 and 0 <= u <= 12:
                buckets[(r // 24, g // 24, b // 24)] += 1
    print("\n== south band color histogram (top 12, x24 buckets) ==")
    tot = sum(buckets.values())
    for (r, g, b), n in buckets.most_common(12):
        print(f"  ({r * 24 + 12:3d},{g * 24 + 12:3d},{b * 24 + 12:3d})  {100 * n / tot:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
