#!/usr/bin/env python
"""Generate the animated character atlas for the office simulation.

    python infra/scripts/make_character_atlas.py

Writes `atlas.png` + `atlas.json` into `apps/web/public/assets/office/`.
The atlas is the *animated* character source: 8 looks x 4 facings with
4-frame walk cycles, 2-frame idle breathing, 2-frame typing and seated
poses. The renderer (`PersonRenderer.ts`) picks frames from the JSON.

This replaces the old single-pose `characters/*.png` set, which could
only slide a static sprite around the room. This generator is what
makes people *walk* — a real stride with planted and lifted feet, arm
swing, and a 1px contact bob — not a glide.

Stdlib only: PNGs are written by hand with zlib+struct (no Pillow),
matching `make_placeholder_atlas.py` in this directory.

Frame naming (consumed by the renderer):

    look_{L}_{anim}_{dir}_{frame}    anim in walk|idle|type; frame 0..3 or 0..1
    look_{L}_sit_{dir}               dir in s|n   (meeting-room seats)

Directions: s = toward camera, n = away, e = screen-right, w = screen-left
(w is the e shape mirrored at build time).

Layout: 64x64 cells, 4 per row, feet anchored at (32, 62) of the cell —
the renderer draws bottom-center so feet land on the tile.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "assets" / "office" / "characters"
TS_OUT = Path(__file__).resolve().parents[2] / "apps" / "web" / "src" / "game" / "engine" / "atlasFrames.generated.ts"

CW, CH = 64, 64          # cell size
CX = 32                  # horizontal center of a cell
FY = 62                  # feet (ground) line inside a cell
COLUMNS = 4

RGBA = tuple[int, int, int, int]
TRANSPARENT: RGBA = (0, 0, 0, 0)

# ── Shared palette ────────────────────────────────────────────────────
OUTLINE = (0x1A, 0x1E, 0x28, 255)      # shared dark outline
SHOE = (0x22, 0x26, 0x30, 255)
SKIN_BLUSH = (0xB4, 0x7A, 0x52, 255)


def rgba(c: tuple[int, int, int] | RGBA) -> RGBA:
    return c if len(c) == 4 else (c[0], c[1], c[2], 255)


def shade(c: tuple[int, int, int] | RGBA, k: float) -> RGBA:
    r, g, b, a = rgba(c)
    return (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)), a)


# ── Looks ─────────────────────────────────────────────────────────────


class Look:
    __slots__ = (
        "shirt", "collar", "pants", "skin", "hair", "style",
        "shirt_sh", "shirt_hi", "pants_sh", "skin_sh", "hair_hi",
    )

    def __init__(self, shirt: tuple[int, int, int], collar: tuple[int, int, int],
                 pants: tuple[int, int, int], skin: tuple[int, int, int],
                 hair: tuple[int, int, int], style: str) -> None:
        self.shirt = rgba(shirt)
        self.collar = rgba(collar)
        self.pants = rgba(pants)
        self.skin = rgba(skin)
        self.hair = rgba(hair)
        self.style = style
        self.shirt_sh = shade(shirt, 0.74)
        self.shirt_hi = shade(shirt, 1.22)
        self.pants_sh = shade(pants, 0.74)
        self.skin_sh = shade(skin, 0.86)
        self.hair_hi = shade(hair, 1.35)


LOOKS: list[Look] = [
    Look((0x2E, 0x36, 0x44), (0xE8, 0xEC, 0xF2), (0x23, 0x27, 0x30), (0xC9, 0x8D, 0x63), (0x63, 0x63, 0x6B), "part"),   # 0 exec, grey-flecked suit
    Look((0x27, 0x49, 0x6D), (0xCF, 0xE0, 0xF4), (0x2A, 0x2F, 0x3A), (0xE0, 0xAE, 0x86), (0x24, 0x1B, 0x14), "short"),  # 1 manager, navy
    Look((0x1F, 0x7A, 0x6D), (0xEA, 0xF6, 0xF0), (0x6B, 0x5B, 0x43), (0xA7, 0x6B, 0x45), (0x3E, 0x2B, 0x1E), "short"),  # 2 senior, teal + khaki
    Look((0x3D, 0x6B, 0xB5), (0xD8, 0xE6, 0xFA), (0x26, 0x2B, 0x38), (0xD7, 0x9C, 0x74), (0x1E, 0x17, 0x12), "part"),   # 3 engineer, steel blue
    Look((0x8E, 0x4F, 0x6E), (0xF2, 0xE2, 0xEC), (0x30, 0x35, 0x40), (0xC9, 0x8D, 0x63), (0x14, 0x10, 0x14), "curly"),  # 4 engineer, plum, curly
    Look((0x4A, 0x90, 0xD9), (0xE2, 0xF0, 0xFD), (0x3A, 0x41, 0x52), (0xE0, 0xAE, 0x86), (0x6B, 0x4A, 0x2B), "buzz"),   # 5 intern, bright blue
    Look((0x45, 0x58, 0x6B), (0x5A, 0x6E, 0x82), (0x3A, 0x40, 0x48), (0xD7, 0x9C, 0x74), (0x2C, 0x21, 0x19), "short"),  # 6 devops, slate hoodie
    Look((0x3F, 0x7A, 0x8E), (0xE2, 0xF2, 0xF6), (0x2A, 0x2F, 0x3A), (0xA7, 0x6B, 0x45), (0x8E, 0x3B, 0x2F), "long"),   # 7 engineer, auburn long hair
]

# Per-look accessory, drawn over the finished silhouette (keyed by look index).
# 'badge' = ID card clipped at the hip, 'tie' = necktie stripe,
# 'lanyard' = colored strap across the chest, 'headset' = band over the hair.
ACCESSORIES: dict[int, str] = {
    0: "tie",       # exec
    1: "lanyard",   # manager
    2: "badge",     # senior
    3: "badge",     # engineer
    4: "lanyard",   # engineer
    5: "headset",   # intern
    6: "headset",   # devops
    7: "badge",     # engineer
}


# ── PNG writer (same approach as make_placeholder_atlas.py) ──────────


def write_png(path: Path, width: int, height: int, pixels: list[list[RGBA]]) -> None:
    raw = bytearray()
    for row in pixels:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def blank(width: int, height: int) -> list[list[RGBA]]:
    return [[TRANSPARENT for _ in range(width)] for _ in range(height)]


# ── Pixel painter ─────────────────────────────────────────────────────


class Painter:
    """Draws into one cell. x is relative to CX (+x = screen-right);
    `flip` mirrors x (builds the `w` facing from the `e` shapes).
    y is absolute inside the cell."""

    def __init__(self, pixels: list[list[RGBA]], ox: int, oy: int, flip: bool) -> None:
        self.pixels = pixels
        self.ox = ox
        self.oy = oy
        self.flip = flip

    def px(self, x: int, y: int, c: RGBA) -> None:
        if self.flip:
            x = -x
        gx = self.ox + CX + x
        gy = self.oy + y
        if 0 <= gy < len(self.pixels) and 0 <= gx < len(self.pixels[0]):
            self.pixels[gy][gx] = c

    def rect(self, x0: int, y0: int, w: int, h: int, c: RGBA) -> None:
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                self.px(x, y, c)

    def hline(self, x0: int, x1: int, y: int, c: RGBA) -> None:
        for x in range(x0, x1 + 1):
            self.px(x, y, c)


# ── Body parts ────────────────────────────────────────────────────────
# Skeleton (dy = 1px contact bob): head 18..31, neck 31..33, torso
# 34..49, hips 50, legs 50..61, shoes touch FY=62.


def draw_head(p: Painter, lk: Look, dy: int, back: bool = False, profile: bool = False) -> None:
    top = 18 + dy          # skull top (skin starts here, under hair)
    bot = 31 + dy          # chin
    h, hi = lk.hair, lk.hair_hi
    # neck
    p.rect(-2, bot, 5, 3, lk.skin_sh)
    # skull
    p.rect(-6, top, 13, bot - top, lk.skin)
    p.hline(-5, 4, bot - 1, lk.skin_sh)

    if back:
        p.rect(-7, top - 3, 15, bot - top + 4, h)
        p.hline(-6, 6, top - 3, hi)
        if lk.style == "long":
            p.rect(-7, top + 1, 3, bot - top + 2, h)
            p.rect(5, top + 1, 3, bot - top + 2, h)
        return

    # hair styles first (face features paint over fringe edge cleanly)
    p.rect(-7, top - 3, 15, 4, h)                       # crown band
    p.hline(-6, 6, top - 3, hi)
    if lk.style == "short":
        p.rect(-7, top + 1, 2, 4, h)
        p.rect(6, top + 1, 2, 4, h)
        p.rect(-2, top + 1, 5, 1, h)
    elif lk.style == "part":
        p.rect(-7, top + 1, 2, 5, h)
        p.rect(6, top + 1, 2, 4, h)
        p.rect(-1, top + 1, 6, 1, h)
        p.rect(-6, top - 1, 5, 1, hi)
    elif lk.style == "curly":
        for dx, dy2 in ((-7, 0), (-4, -1), (0, -1), (4, 0), (6, 1)):
            p.rect(dx, top + dy2, 3, 3, h)
        p.rect(-7, top + 2, 2, 3, h)
        p.rect(6, top + 2, 2, 3, h)
    elif lk.style == "buzz":
        p.rect(-7, top - 2, 15, 2, h)
        p.rect(-7, top + 0, 2, 3, h)
        p.rect(6, top + 0, 2, 3, h)
    elif lk.style == "long":
        p.rect(-7, top + 1, 3, 10, h)                   # falls past the jaw
        p.rect(5, top + 1, 3, 10, h)
        p.rect(-4, top + 1, 9, 1, h)
        p.rect(-7, top + 1, 2, 3, hi)

    if profile:
        p.rect(2, top + 6, 2, 2, OUTLINE)               # single eye, +x
        p.px(3, bot - 2, SKIN_BLUSH)
    else:
        p.rect(-4, top + 6, 2, 2, OUTLINE)
        p.rect(3, top + 6, 2, 2, OUTLINE)
        p.px(0, bot - 2, SKIN_BLUSH)


def draw_torso_front(p: Painter, lk: Look, dy: int) -> None:
    top = 34 + dy
    p.rect(-9, top, 18, 16, lk.shirt)
    p.rect(-9, top, 1, 16, lk.shirt_sh)
    p.rect(8, top, 1, 16, lk.shirt_sh)
    p.hline(-8, 7, top + 15, shade(lk.shirt, 0.6))
    p.rect(-2, top, 5, 3, lk.collar)
    p.rect(-7, top + 1, 2, 2, lk.shirt_hi)
    p.rect(-11, top + 1, 3, 12, lk.shirt_sh)            # arms
    p.rect(9, top + 1, 3, 12, lk.shirt_sh)
    p.rect(-11, top + 13, 3, 3, lk.skin)                # hands
    p.rect(9, top + 13, 3, 3, lk.skin)
    p.rect(-8, top + 14, 16, 2, OUTLINE)                # belt


def draw_torso_side(p: Painter, lk: Look, dy: int) -> None:
    top = 34 + dy
    p.rect(-6, top, 12, 16, lk.shirt)
    p.rect(-6, top, 1, 16, lk.shirt_sh)
    p.hline(-5, 4, top + 15, shade(lk.shirt, 0.6))
    p.rect(-1, top, 4, 2, lk.collar)
    p.rect(-4, top + 1, 2, 2, lk.shirt_hi)
    p.rect(-8, top + 1, 3, 13, lk.shirt_sh)             # far arm
    p.rect(5, top + 1, 3, 13, lk.shirt_sh)              # near arm
    p.rect(-5, top + 14, 10, 2, OUTLINE)


def draw_torso_back(p: Painter, lk: Look, dy: int) -> None:
    top = 34 + dy
    p.rect(-8, top, 17, 16, lk.shirt_sh)
    p.rect(-8, top, 17, 1, lk.shirt)
    p.hline(-7, 7, top + 15, shade(lk.shirt, 0.55))
    p.rect(-11, top + 1, 3, 13, shade(lk.shirt, 0.62))
    p.rect(9, top + 1, 3, 13, shade(lk.shirt, 0.62))


def draw_legs_front(p: Painter, lk: Look, llift: int, rlift: int,
                    ldx: int = 0, rdx: int = 0) -> None:
    for dx, lift in ((ldx - 4, llift), (rdx + 1, rlift)):
        p.rect(dx, 50, 6, 12 - lift, lk.pants)
        p.rect(dx, 50, 2, 12 - lift, lk.pants_sh)
        p.rect(dx - 1, 60 - lift, 8, 2, SHOE)


def draw_legs_side(p: Painter, lk: Look, fx: int, flift: int, bx: int, blift: int) -> None:
    """Side legs: front leg (+x, forward) and back leg."""
    p.rect(bx, 50, 5, 10 - blift, lk.pants_sh)
    p.rect(bx - 1, 58 - blift, 6, 2, SHOE)
    p.rect(fx, 50, 5, 11 - flift, lk.pants)
    p.rect(fx - 1, 60 - flift, 7, 2, SHOE)


# ── Animations ────────────────────────────────────────────────────────
# Walk: frames 0 & 2 are contact poses (1px bob), 1 & 3 are passes.


def draw_walk_front(p: Painter, lk: Look, f: int) -> None:
    dy = 1 if f in (0, 2) else 0
    draw_head(p, lk, dy)
    draw_torso_front(p, lk, dy)
    if f == 0:
        draw_legs_front(p, lk, 0, 4, ldx=-1)
        p.rect(-11, 36, 3, 11, lk.shirt_sh)             # arm swing
        p.rect(9, 33, 3, 12, lk.shirt_sh)
    elif f == 1:
        draw_legs_front(p, lk, 2, 2)
    elif f == 2:
        draw_legs_front(p, lk, 4, 0, rdx=1)
        p.rect(-11, 33, 3, 12, lk.shirt_sh)
        p.rect(9, 36, 3, 11, lk.shirt_sh)
    else:
        draw_legs_front(p, lk, 2, 2)


def draw_walk_side(p: Painter, lk: Look, f: int) -> None:
    dy = 1 if f in (0, 2) else 0
    draw_head(p, lk, dy, profile=True)
    draw_torso_side(p, lk, dy)
    if f == 0:                                          # full stride
        draw_legs_side(p, lk, fx=2, flift=0, bx=-5, blift=2)
        p.rect(5, 34, 3, 12, lk.shirt_sh)               # arms opposite legs
        p.rect(-9, 33, 3, 12, lk.shirt_sh)
    elif f == 1:                                        # passing
        draw_legs_side(p, lk, fx=-1, flift=1, bx=-3, blift=1)
        p.rect(5, 35, 3, 12, lk.shirt_sh)
        p.rect(-8, 35, 3, 12, lk.shirt_sh)
    elif f == 2:                                        # opposite stride
        draw_legs_side(p, lk, fx=-4, flift=0, bx=1, blift=2)
        p.rect(-9, 34, 3, 12, lk.shirt_sh)
        p.rect(5, 33, 3, 12, lk.shirt_sh)
    else:
        draw_legs_side(p, lk, fx=-1, flift=1, bx=-3, blift=1)
        p.rect(5, 35, 3, 12, lk.shirt_sh)
        p.rect(-8, 35, 3, 12, lk.shirt_sh)


def draw_walk_back(p: Painter, lk: Look, f: int) -> None:
    dy = 1 if f in (0, 2) else 0
    draw_head(p, lk, dy, back=True)
    draw_torso_back(p, lk, dy)
    if f == 0:
        draw_legs_front(p, lk, 0, 4, ldx=-1)
    elif f == 1:
        draw_legs_front(p, lk, 2, 2)
    elif f == 2:
        draw_legs_front(p, lk, 4, 0, rdx=1)
    else:
        draw_legs_front(p, lk, 2, 2)


def draw_idle_front(p: Painter, lk: Look, f: int) -> None:
    dy = f
    draw_head(p, lk, dy)
    draw_torso_front(p, lk, dy)


def draw_idle_side(p: Painter, lk: Look, f: int) -> None:
    dy = f
    draw_head(p, lk, dy, profile=True)
    draw_torso_side(p, lk, dy)


def draw_idle_back(p: Painter, lk: Look, f: int) -> None:
    dy = f
    draw_head(p, lk, dy, back=True)
    draw_torso_back(p, lk, dy)


def draw_type_front(p: Painter, lk: Look, f: int) -> None:
    """Standing at a desk: torso + forearms reaching forward, typing."""
    draw_head(p, lk, 0)
    top = 40
    p.rect(-7, top, 15, 14, lk.shirt)
    p.rect(-7, top, 1, 14, lk.shirt_sh)
    p.rect(7, top, 1, 14, lk.shirt_sh)
    p.rect(-2, top, 5, 2, lk.collar)
    p.rect(-5, top + 1, 2, 2, lk.shirt_hi)
    j = 1 if f == 1 else 0
    p.rect(-9, top + 7, 3, 6, lk.shirt_sh)              # forearms to desk
    p.rect(7, top + 7, 3, 6, lk.shirt_sh)
    p.rect(-9, top + 12 + j, 3, 3, lk.skin)             # alternating hands
    p.rect(7, top + 13 - j, 3, 3, lk.skin)


def draw_type_side(p: Painter, lk: Look, f: int) -> None:
    draw_head(p, lk, 0, profile=True)
    top = 40
    p.rect(-5, top, 11, 14, lk.shirt)
    p.rect(-5, top, 1, 14, lk.shirt_sh)
    p.rect(-1, top, 4, 2, lk.collar)
    j = 1 if f == 1 else 0
    p.rect(5, top + 7 + j, 5, 3, lk.shirt_sh)           # arm toward desk
    p.rect(9, top + 8 + j, 3, 3, lk.skin)
    p.rect(-4, top + 13, 10, 1, shade(lk.shirt, 0.6))


def draw_type_back(p: Painter, lk: Look, _f: int) -> None:
    draw_head(p, lk, 0, back=True)
    top = 40
    p.rect(-7, top, 15, 14, lk.shirt_sh)
    p.rect(-7, top, 15, 1, lk.shirt)


def draw_sit_front(p: Painter, lk: Look, _f: int) -> None:
    """Full seated pose for meeting-room chairs, facing the table."""
    draw_head(p, lk, 0)
    top = 38
    p.rect(-7, top, 15, 12, lk.shirt)
    p.rect(-7, top, 1, 12, lk.shirt_sh)
    p.rect(7, top, 1, 12, lk.shirt_sh)
    p.rect(-2, top, 5, 2, lk.collar)
    p.rect(-6, 50, 5, 6, lk.pants)                      # thighs
    p.rect(2, 50, 5, 6, lk.pants)
    p.rect(-6, 55, 4, 7, lk.pants_sh)                   # shins
    p.rect(3, 55, 4, 7, lk.pants_sh)
    p.rect(-7, 61, 6, 2, SHOE)
    p.rect(2, 61, 6, 2, SHOE)


def draw_sit_back(p: Painter, lk: Look, _f: int) -> None:
    draw_head(p, lk, 0, back=True)
    top = 38
    p.rect(-7, top, 15, 12, lk.shirt_sh)
    p.rect(-7, top, 15, 1, lk.shirt)
    p.rect(-6, 50, 4, 11, lk.pants_sh)
    p.rect(3, 50, 4, 11, lk.pants_sh)
    p.rect(-7, 60, 6, 2, SHOE)
    p.rect(2, 60, 6, 2, SHOE)


# ── Accessories ───────────────────────────────────────────────────────
# Drawn OVER the finished silhouette; front-facing only (back/side frames
# skip most of them, which also reads as depth). Colors are fixed so they
# double as identity signals.

BADGE = (0xF2, 0xC9, 0x4A, 255)       # yellow ID card
BADGE_SH = (0xC9, 0xA0, 0x2E, 255)
LANYARD = (0x3D, 0x7B, 0xFF, 255)     # blue strap
TIE = (0x7A, 0x2E, 0x3C, 255)         # burgundy tie
HEADSET = (0x2B, 0x2F, 0x3A, 255)     # dark band + mic


def draw_accessory(p: Painter, lk: Look, facing: str, anim: str) -> None:
    acc = ACCESSORIES.get(LOOKS.index(lk))
    if not acc:
        return
    top = 34
    if facing in ("s", "w", "e") and anim != "sit":
        if acc == "tie":
            p.rect(-1, top + 3, 3, 9, TIE)
            p.px(0, top + 12, TIE)
        elif acc == "lanyard":
            for dx in (-4, -3, 3, 4):
                p.px(dx, top + 2, LANYARD)
                p.px(dx + (1 if dx < 0 else -1), top + 3, LANYARD)
            p.rect(-1, top + 10, 3, 5, BADGE)       # card on the chest
            p.hline(-1, 1, top + 14, BADGE_SH)
        elif acc == "badge":
            p.rect(3, top + 12, 4, 5, BADGE)        # clipped at the hip
            p.hline(3, 6, top + 16, BADGE_SH)
    if acc == "headset" and facing != "n":
        # band over the crown + ear pad on the visible side
        p.hline(-6, 5, 15, HEADSET)
        p.rect(6, 17, 3, 4, HEADSET)
        if facing in ("w", "e"):
            p.rect(-8, 17, 2, 4, HEADSET)


def draw_outline(pixels: list[list[RGBA]], ox: int, oy: int) -> None:
    """1px dark contour around the silhouette (only against transparency)."""
    src = [row[:] for row in pixels[oy:oy + CH]]
    H = len(src)
    W = len(src[0]) if H else 0
    for y in range(oy, oy + CH):
        for x in range(ox, ox + CW):
            c = pixels[y][x]
            if c[3] > 0:
                continue
            near = False
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                yy, xx = y + dy, x + dx
                ly = yy - oy
                if 0 <= ly < H and 0 <= xx - ox < W:
                    if src[ly][xx - ox][3] > 60:
                        near = True
                        break
            if near:
                pixels[y][x] = OUTLINE


DRAWERS: dict[tuple[str, str], object] = {
    ("walk", "s"): draw_walk_front,
    ("walk", "e"): draw_walk_side,
    ("walk", "w"): draw_walk_side,
    ("walk", "n"): draw_walk_back,
    ("idle", "s"): draw_idle_front,
    ("idle", "e"): draw_idle_side,
    ("idle", "w"): draw_idle_side,
    ("idle", "n"): draw_idle_back,
    ("type", "s"): draw_type_front,
    ("type", "e"): draw_type_side,
    ("type", "w"): draw_type_side,
    ("type", "n"): draw_type_back,
    ("sit", "s"): draw_sit_front,
    ("sit", "n"): draw_sit_back,
}

# (anim, dirs, frames-per-dir); sit frames are single and unnumbered.
ANIMS: list[tuple[str, list[str], int]] = [
    ("walk", ["s", "w", "n", "e"], 4),
    ("idle", ["s", "w", "n", "e"], 2),
    ("type", ["s", "w", "n", "e"], 2),
    ("sit", ["s", "n"], 1),
]


def frames_per_look() -> int:
    return sum(len(dirs) * n for _, dirs, n in ANIMS)


# ── Main ──────────────────────────────────────────────────────────────


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    per_look = frames_per_look()
    rows_per_look = (per_look + COLUMNS - 1) // COLUMNS
    width = COLUMNS * CW
    height = rows_per_look * len(LOOKS) * CH
    pixels = blank(width, height)
    frames: dict[str, dict[str, object]] = {}

    for li, lk in enumerate(LOOKS):
        cell = 0
        for anim, dirs, nframes in ANIMS:
            for d in dirs:
                for f in range(nframes):
                    name = (
                        f"look_{li}_{anim}_{d}_{f}"
                        if nframes > 1
                        else f"look_{li}_{anim}_{d}"
                    )
                    col = cell % COLUMNS
                    row = cell // COLUMNS
                    ox = col * CW
                    oy = (li * rows_per_look + row) * CH
                    painter = Painter(pixels, ox, oy, d == "w")
                    DRAWERS[(anim, d)](painter, lk, f)  # type: ignore[operator]
                    draw_accessory(painter, lk, d, anim)
                    draw_outline(pixels, ox, oy)
                    frames[name] = {
                        "frame": {"x": ox, "y": oy, "w": CW, "h": CH},
                        "anchor": {"x": CX, "y": FY},
                    }
                    cell += 1
        assert cell == per_look, f"look {li}: {cell} != {per_look}"

    write_png(OUT / "atlas.png", width, height, pixels)
    atlas = {
        "frames": frames,
        "meta": {"image": "atlas.png", "size": {"w": width, "h": height}, "scale": "1"},
    }
    (OUT / "atlas.json").write_text(json.dumps(atlas, indent=2), encoding="utf-8")

    # Frame table as a TS module: the office renderer imports it directly.
    # (src/game may not fetch() — office-isolation invariant — so the JSON
    # is compile-time data, not a runtime request.)
    ts = [
        "/**",
        " * GENERATED by infra/scripts/make_character_atlas.py — do not edit.",
        " * Frame table for the animated character atlas (atlas.png).",
        " */",
        "",
        "export interface AtlasFrame {",
        "  frame: { x: number; y: number; w: number; h: number }",
        "  anchor: { x: number; y: number }",
        "}",
        "",
        "export const ATLAS_FRAMES: Record<string, AtlasFrame> =",
        json.dumps(frames, indent=2),
        "",
    ]
    TS_OUT.write_text("\n".join(ts), encoding="utf-8")

    print(f"  atlas.png  {width}x{height}, {len(frames)} frames, {len(LOOKS)} looks")
    print(f"  atlas.json frame table ({per_look} frames per look)")
    print(f"  atlasFrames.generated.ts")
    print(f"\n  -> {OUT}")
    print(f"  -> {TS_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
