#!/usr/bin/env python
"""Generate placeholder art so the scene is never blocked on assets.

    python infra/scripts/make_placeholder_atlas.py

Writes flat-coloured isometric tiles and simple character sprites to
`apps/web/public/assets/office/`. Everything in the scene works with these;
real art drops in by replacing two PNGs and one JSON, with zero code change.

That ordering is deliberate. Building the system against placeholders and
swapping art last means the visual phase cannot be blocked by a licence
decision -- and `docs/07-OFFICE-SIMULATION.md` section 4.2 is clear that a
hackathon is not a licence exemption.

Uses only the standard library: PNGs are written by hand with `zlib` and
`struct`, so this needs no Pillow and no install step.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "apps" / "web" / "public" / "assets" / "office"

TILE_W, TILE_H = 64, 64          # 32px of overhang above the 64x32 diamond
DIAMOND_H = 32
CHAR_W, CHAR_H = 32, 48

# Ink palette from `docs/04-UI-UX-BRIEF.md` section 2. The placeholder floor
# is the console's own surface colours, so the canvas already looks like part
# of the product rather than like a programmer-art stand-in.
RGBA = tuple[int, int, int, int]

TILE_COLOURS: dict[str, RGBA] = {
    "floor_grey": (0x1C, 0x29, 0x3C, 255),
    "floor_wood": (0x2A, 0x24, 0x1C, 255),
    "floor_carpet_red": (0x2E, 0x1E, 0x24, 255),
    "brick_nw": (0x25, 0x32, 0x48, 255),
    "brick_ne": (0x1E, 0x29, 0x3C, 255),
    "wall_cap": (0x33, 0x45, 0x5F, 255),
    "window_ne": (0x3D, 0x7B, 0xFF, 120),
    "desk_n": (0x3A, 0x30, 0x26, 255),
    "desk_e": (0x3A, 0x30, 0x26, 255),
    "desk_s": (0x3A, 0x30, 0x26, 255),
    "desk_w": (0x3A, 0x30, 0x26, 255),
    "chair_n": (0x27, 0x37, 0x4E, 255),
    "chair_e": (0x27, 0x37, 0x4E, 255),
    "chair_s": (0x27, 0x37, 0x4E, 255),
    "chair_w": (0x27, 0x37, 0x4E, 255),
    "monitor": (0x0D, 0x14, 0x20, 255),
    "partition": (0x33, 0x45, 0x5F, 255),
    "bookshelf": (0x3A, 0x30, 0x26, 255),
    "plant_tall": (0x3F, 0xCF, 0x8E, 255),
    "plant_small": (0x3F, 0xCF, 0x8E, 255),
    "water_cooler": (0x93, 0xA4, 0xBD, 255),
    "coffee": (0xE8, 0xC4, 0x68, 255),
    "whiteboard": (0xE6, 0xED, 0xF7, 255),
    "server_rack": (0x1C, 0x29, 0x3C, 255),
    "printer": (0x5C, 0x6E, 0x89, 255),
    "meeting_table": (0x3A, 0x30, 0x26, 255),
}

# Shirt colours, assigned deterministically from the employee id.
SHIRTS: tuple[RGBA, ...] = (
    (0x3D, 0x7B, 0xFF, 255),
    (0x3F, 0xCF, 0x8E, 255),
    (0xF2, 0xA7, 0x3B, 255),
    (0xA8, 0x55, 0xF7, 255),
    (0xE5, 0x48, 0x4D, 255),
    (0xE6, 0x68, 0xC3, 255),
    (0x93, 0xA4, 0xBD, 255),
    (0xE8, 0xC4, 0x68, 255),
)

SKIN: RGBA = (0xC8, 0xA0, 0x7A, 255)
TRANSPARENT: RGBA = (0, 0, 0, 0)

FACINGS = ("s", "w", "n", "e")
ANIMATIONS = ("idle", "walk", "type")
FRAMES = {"idle": 2, "walk": 4, "type": 2}


# ──────────────────────────────────────────────────────────────────────
# Minimal PNG writer
# ──────────────────────────────────────────────────────────────────────


def write_png(path: Path, width: int, height: int, pixels: list[list[RGBA]]) -> None:
    """RGBA PNG, no dependencies.

    Pillow would be one more thing to install before a scene can render, and
    a flat-colour atlas does not need an imaging library.
    """
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0
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
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def blank(width: int, height: int) -> list[list[RGBA]]:
    return [[TRANSPARENT for _ in range(width)] for _ in range(height)]


# ──────────────────────────────────────────────────────────────────────
# Tiles
# ──────────────────────────────────────────────────────────────────────


def draw_diamond(
    pixels: list[list[RGBA]], ox: int, oy: int, colour: RGBA, raised: int = 0
) -> None:
    """A 2:1 isometric floor diamond, optionally extruded upward.

    The extrusion is what makes a desk read as a desk rather than as a floor
    tile in a different colour, and it is drawn darker on one side so the
    depth sort has something to be consistent with.
    """
    half_w, half_h = TILE_W // 2, DIAMOND_H // 2

    if raised:
        side = tuple(max(0, int(c * 0.65)) for c in colour[:3]) + (colour[3],)
        for y in range(DIAMOND_H):
            span = int((1 - abs(y - half_h) / half_h) * half_w)
            for lift in range(raised):
                py = oy + y - lift
                if 0 <= py < len(pixels):
                    for x in range(-span, span):
                        px = ox + half_w + x
                        if 0 <= px < len(pixels[0]):
                            pixels[py][px] = side  # type: ignore[assignment]

    for y in range(DIAMOND_H):
        span = int((1 - abs(y - half_h) / half_h) * half_w)
        py = oy + y - raised
        if not (0 <= py < len(pixels)):
            continue
        for x in range(-span, span):
            px = ox + half_w + x
            if 0 <= px < len(pixels[0]):
                pixels[py][px] = colour


def build_tileset() -> dict[str, object]:
    names = list(TILE_COLOURS)
    columns = 8
    rows = (len(names) + columns - 1) // columns
    width, height = columns * TILE_W, rows * TILE_H
    pixels = blank(width, height)
    frames: dict[str, object] = {}

    for index, name in enumerate(names):
        col, row = index % columns, index // columns
        ox, oy = col * TILE_W, row * TILE_H
        colour = TILE_COLOURS[name]

        # Furniture sits proud of the floor; floors and walls do not.
        raised = 0 if name.startswith(("floor_", "brick_", "window_")) else 10
        draw_diamond(pixels, ox, oy + TILE_H - DIAMOND_H - raised, colour, raised)

        frames[name] = {
            "frame": {"x": ox, "y": oy, "w": TILE_W, "h": TILE_H},
            "sourceSize": {"w": TILE_W, "h": TILE_H},
            "spriteSourceSize": {"x": 0, "y": 0, "w": TILE_W, "h": TILE_H},
        }

    write_png(OUT / "tileset.png", width, height, pixels)
    return {
        "frames": frames,
        "meta": {"image": "tileset.png", "size": {"w": width, "h": height}, "scale": "1"},
    }


# ──────────────────────────────────────────────────────────────────────
# Characters
# ──────────────────────────────────────────────────────────────────────


def draw_character(
    pixels: list[list[RGBA]], ox: int, oy: int, shirt: RGBA, facing: str, bob: int
) -> None:
    """A blocky figure: head, torso, legs, and a facing marker.

    Detail is not the point -- readability at 0.5x zoom is. The facing marker
    is a single lighter column, which is enough to tell which way someone is
    turned from across a room.
    """
    head_y = oy + 8 + bob

    for y in range(head_y, head_y + 9):
        for x in range(ox + 12, ox + 20):
            pixels[y][x] = SKIN

    for y in range(head_y + 9, head_y + 28):
        for x in range(ox + 10, ox + 22):
            pixels[y][x] = shirt

    legs = tuple(max(0, int(c * 0.5)) for c in shirt[:3]) + (255,)
    for y in range(head_y + 28, head_y + 38):
        for x in range(ox + 11, ox + 15):
            pixels[y][x] = legs  # type: ignore[assignment]
        for x in range(ox + 17, ox + 21):
            pixels[y][x] = legs  # type: ignore[assignment]

    marker = (0xE6, 0xED, 0xF7, 200)
    if facing == "s":
        columns = range(ox + 14, ox + 18)
    elif facing == "n":
        columns = range(ox + 14, ox + 18)
    elif facing == "e":
        columns = range(ox + 19, ox + 22)
    else:
        columns = range(ox + 10, ox + 13)

    row = head_y + 4 if facing != "n" else head_y + 1
    for x in columns:
        pixels[row][x] = marker


def build_characters() -> dict[str, object]:
    """Eight base sprites, each with idle/walk/type across four facings."""
    per_character = sum(FRAMES[a] for a in ANIMATIONS) * len(FACINGS)
    columns = per_character
    rows = len(SHIRTS)
    width, height = columns * CHAR_W, rows * CHAR_H
    pixels = blank(width, height)
    frames: dict[str, object] = {}

    for character, shirt in enumerate(SHIRTS):
        column = 0
        for animation in ANIMATIONS:
            for facing in FACINGS:
                for frame in range(FRAMES[animation]):
                    ox, oy = column * CHAR_W, character * CHAR_H
                    # Two-frame idle bob, four-frame walk cycle.
                    bob = frame % 2 if animation != "walk" else (frame % 4) // 2
                    draw_character(pixels, ox, oy, shirt, facing, bob)

                    key = f"char_{character:02d}_{animation}_{facing}_{frame}"
                    frames[key] = {
                        "frame": {"x": ox, "y": oy, "w": CHAR_W, "h": CHAR_H},
                        "sourceSize": {"w": CHAR_W, "h": CHAR_H},
                        "spriteSourceSize": {"x": 0, "y": 0, "w": CHAR_W, "h": CHAR_H},
                    }
                    column += 1

    write_png(OUT / "characters.png", width, height, pixels)
    return {
        "frames": frames,
        "meta": {
            "image": "characters.png",
            "size": {"w": width, "h": height},
            "scale": "1",
        },
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    tileset = build_tileset()
    characters = build_characters()

    (OUT / "tileset.json").write_text(json.dumps(tileset, indent=2), encoding="utf-8")
    (OUT / "characters.json").write_text(json.dumps(characters, indent=2), encoding="utf-8")

    print(f"  tileset.png      {len(TILE_COLOURS)} tiles")
    print(f"  characters.png   {len(SHIRTS)} characters x {len(FACINGS)} facings")
    print(f"  tileset.json / characters.json")
    print(f"\n  -> {OUT}")
    print("\n  Replace the two PNGs and their JSON to swap in real art.")
    print("  Record every asset in CREDITS.md as you add it, not at the end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
