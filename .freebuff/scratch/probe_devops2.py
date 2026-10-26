#!/usr/bin/env python
"""Probe #2 for the shipped devops art: measure, don't guess.

1. NE (back) wall band: per-u column classification -> wall extent, lamp,
   window, rack back-projection, clean cloneable columns.
2. NW (left) wall band: per-v row classification -> hole runs + clean rows.
3. Junk: opaque clusters outside the room diamond, above the plinth line.
4. Floor: dense verified-clean tile map (mirror-source candidates).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path("/Users/kanishk_pandey/Desktop/as/Agent-Shield-")
sys.path.insert(0, str(ROOT / "infra" / "scripts"))

from extract_furniture import read_png, sample_floor_palette, near, BG  # noqa: E402

SHIP = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"
CAL = (487, 172)
RW, RH = 12, 11
TW_HALF, TH_HALF = 32, 16


def to_px(u: float, v: float) -> tuple[float, float]:
    return ((u - v) * TW_HALF + CAL[0], (u + v) * TH_HALF + CAL[1])


def back(X: float, Y: float) -> tuple[float, float]:
    a = (X - CAL[0]) / TW_HALF
    b = (Y - CAL[1]) / TH_HALF
    return ((a + b) / 2, (b - a) / 2)


def classify_color(r: int, g: int, b: int, a: int) -> str:
    if a < 40:
        return "void"
    if abs(r - BG[0]) < 14 and abs(g - BG[1]) < 14 and abs(b - BG[2]) < 14:
        return "bg"
    if b > r + 12 and b > g + 8:
        return "window"
    if r > 195 and g > 105 and b < g:
        return "warm"
    lum = (r + g + b) / 3
    if lum < 60:
        return "dark"
    if r > g > b and r - b > 30:
        return "brick"
    return "other"


def edge_y(x: float) -> float:
    x_N, y_N = CAL
    Wx, Wy = x_N - RH * 32, y_N + RH * 16
    Sx, Sy = x_N + (RW - RH) * 32, y_N + (RW + RH) * 16
    Ex = x_N + RW * 32
    if x <= Sx:
        return Wy + 0.5 * (x - Wx)
    if x <= Ex:
        return Sy - 0.5 * (x - Sx)
    return Ey if (Ey := y_N + RW * 16) else 0


def main() -> int:
    w, h, px = read_png(SHIP / "devops.png")
    print(f"canvas {w}x{h}")

    # ── 1. NE (back) wall band ─────────────────────────────────────────
    print("\n== NE wall band: per-u classification over v in [-2.6, 0.0] ==")
    print("  u     brick warm window dark  void other  -> verdict")
    for uq in range(-5, 50):  # u = uq/4
        u = uq / 4
        counts: dict[str, int] = {}
        v = -2.6
        while v <= 0.0:
            X, Y = to_px(u, v)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h:
                c = classify_color(*px[yi][xi])
            else:
                c = "void"
            counts[c] = counts.get(c, 0) + 1
            v += 0.15
        tot = sum(counts.values())
        pct = {k: round(100 * n / tot) for k, n in counts.items()}
        print(
            f"  {u:5.2f}  {pct.get('brick', 0):4d} {pct.get('warm', 0):4d}"
            f" {pct.get('window', 0):4d} {pct.get('dark', 0):4d}"
            f" {pct.get('void', 0) + pct.get('bg', 0):4d} {pct.get('other', 0):4d}"
        )

    # ── 2. NW (left) wall band ─────────────────────────────────────────
    print("\n== NW wall band: per-v classification over u in [-2.6, 0.0] ==")
    print("  v     brick warm window dark  void other")
    for vq in range(-5, 47):  # v = vq/4
        v = vq / 4
        counts: dict[str, int] = {}
        u = -2.6
        while u <= 0.0:
            X, Y = to_px(u, v)
            xi, yi = int(X), int(Y)
            if 0 <= xi < w and 0 <= yi < h:
                c = classify_color(*px[yi][xi])
            else:
                c = "void"
            counts[c] = counts.get(c, 0) + 1
            u += 0.15
        tot = sum(counts.values())
        pct = {k: round(100 * n / tot) for k, n in counts.items()}
        print(
            f"  {v:5.2f}  {pct.get('brick', 0):4d} {pct.get('warm', 0):4d}"
            f" {pct.get('window', 0):4d} {pct.get('dark', 0):4d}"
            f" {pct.get('void', 0) + pct.get('bg', 0):4d} {pct.get('other', 0):4d}"
        )

    # ── 3. junk above the plinth, outside the diamond ──────────────────
    print("\n== junk clusters: opaque, above edge line, u>12.05 or v>11.05 ==")
    junk: list[tuple[int, int]] = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[y][x]
            if a < 40:
                continue
            if y > edge_y(x) - 2:
                continue
            u, v = back(x + 0.5, y + 0.5)
            if u > 12.05 or v > 11.05:
                # ignore true wall regions (NE: v<-0.02, NW: u<-0.02)
                if v < -0.02 or u < -0.02:
                    continue
                junk.append((x, y))
    if junk:
        xs = [p[0] for p in junk]
        ys = [p[1] for p in junk]
        print(f"  {len(junk)}px  bbox x[{min(xs)}..{max(xs)}] y[{min(ys)}..{max(ys)}]")
        uvs = [back(x + 0.5, y + 0.5) for x, y in junk[:: max(1, len(junk) // 12)]]
        for u, v in uvs:
            print(f"    sample u={u:6.2f} v={v:6.2f}")
    else:
        print("  none")

    # ── 4. floor verified-clean tile map ───────────────────────────────
    floor = sample_floor_palette(px, w, h, {"o": (0, 0), "s": (RW, RH), "cal": CAL})
    base = list(floor)
    for k in (0.85, 0.7, 0.55, 0.45):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base]

    means: dict[tuple[int, int], tuple[float, float, float]] = {}
    clean: list[list[bool]] = [[False] * RW for _ in range(RH)]
    for j in range(RH):
        for i in range(RW):
            good = True
            acc = [0.0, 0.0, 0.0]
            n = 0
            for iy in range(16):
                for ix in range(16):
                    X, Y = to_px(i + 0.04 + 0.058 * ix, j + 0.04 + 0.058 * iy)
                    xi, yi = int(X), int(Y)
                    if not (0 <= xi < w and 0 <= yi < h):
                        good = False
                        break
                    r, g, b, a = px[yi][xi]
                    if a < 200 or not near((r, g, b), floor, 22):
                        good = False
                        break
                    acc[0] += r
                    acc[1] += g
                    acc[2] += b
                    n += 1
                if not good:
                    break
            clean[j][i] = good and n > 0
            means[(i, j)] = (acc[0] / n, acc[1] / n, acc[2] / n) if n else (0, 0, 0)
    print("\n== verified-clean floor tiles (dense, 100% floor) ==")
    for j in range(RH):
        print(f"  {j:2d} {''.join('.' if c else 'x' for c in clean[j])}")
    all_means = list(means.values())
    modal = tuple(sorted(ch)[len(ch) // 2] for ch in zip(*all_means))
    print(f"  modal tile tone {tuple(round(m) for m in modal)}")
    for (i, j), m in sorted(means.items()):
        if clean[j][i] and abs(m[0] - modal[0]) + abs(m[1] - modal[1]) + abs(m[2] - modal[2]) > 60:
            print(f"  NOTE tone-outlier clean tile ({i},{j}) mean {tuple(round(x) for x in m)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
