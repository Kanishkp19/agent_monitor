#!/usr/bin/env python
"""Extract furniture footprints from the pre-rendered room PNGs.

    python infra/scripts/extract_furniture.py

Per room:
  1. Decode the PNG (stdlib zlib — no Pillow).
  2. Sample the floor palette adaptively from the front band of the room
     diamond (the nearest tiles — never covered by tall furniture in the
     art), so we don't depend on the stale placeholder palette.
  3. "Furniture" = pixels inside the room diamond that are neither floor
     nor the #080D16 void. Flood-fill blobs, merge close ones.
  4. Convert pixel bboxes to room-LOCAL tile coords via the inverse iso
     projection + CALIBRATION offsets (verified against tile centers).

Prints a suggested rect table for Furniture.ts. Calibrated against the
renderer: tile (0,0) local = room origin; +x = screen right-down.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "apps" / "web" / "public" / "assets" / "office" / "rooms"

TW, TH = 64, 32
BG = (0x08, 0x0D, 0x16)

ROOMS: dict[str, dict] = {
    # Shipped layout (WorldRenderer ROOMS + CALIBRATION, post-growth).
    # Extraction itself runs against ARCHIVE_ROOMS below (the warp/growth
    # is lattice-locked, so footprints carry over unchanged).
    "dev_floor":    {"o": (0, 0),  "s": (20, 20), "cal": (680, 173)},
    "managers":     {"o": (20, 0), "s": (12, 11), "cal": (520, 172)},
    "ceo_office":   {"o": (20, 11), "s": (12, 10), "cal": (424, 172)},
    "devops":       {"o": (20, 21), "s": (12, 11), "cal": (487, 172)},
    "meeting_room": {"o": (0, 20), "s": (20, 12), "cal": (423, 173)},
}

# Pre-warp geometry (infra/rooms_v1/) — the art the footprint classifier
# was validated against (matches the user-approved in-game footprints).
ARC = Path(__file__).resolve().parents[1] / "rooms_v1"
ARCHIVE_ROOMS: dict[str, dict] = {
    "dev_floor":    {"o": (0, 0),  "s": (20, 20), "cal": (680, 173)},
    "managers":     {"o": (20, 0), "s": (12, 7),  "cal": (264, 172)},
    "ceo_office":   {"o": (20, 7), "s": (10, 8),  "cal": (296, 172)},
    "devops":       {"o": (20, 15), "s": (10, 8), "cal": (295, 172)},
    "meeting_room": {"o": (0, 20), "s": (16, 12), "cal": (423, 173)},
}

# ── PNG decode (RGBA8) ────────────────────────────────────────────────


def read_png(path: Path) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"not a png: {path}"
    pos = 8
    width = height = 0
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        if tag == b"IHDR":
            width, height, bitd, color, *_ = struct.unpack(">IIBBBBB", chunk)
            assert bitd == 8 and color == 6, f"unsupported {bitd}/{color}"
        elif tag == b"IDAT":
            idat.extend(chunk)
        elif tag == b"IEND":
            break
        pos += 12 + length

    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows: list[list[tuple[int, int, int, int]]] = []
    prev = bytearray(stride)
    off = 0
    for _ in range(height):
        filt = raw[off]
        line = bytearray(raw[off + 1 : off + 1 + stride])
        off += 1 + stride
        if filt == 1:
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif filt == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif filt == 4:
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        prev = line
        rows.append([(line[x], line[x + 1], line[x + 2], line[x + 3]) for x in range(0, stride, 4)])
    return width, height, rows


# ── PNG writer (RGBA8, same recipe as make_character_atlas.py) ───────


def write_png(path: Path, width: int, height: int, pixels) -> None:
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


# ── Projection ────────────────────────────────────────────────────────


def iso_xy(tx: float, ty: float) -> tuple[float, float]:
    return (tx - ty) * (TW / 2), (tx + ty) * (TH / 2)


def make_pixel_to_local(room: dict):
    ox, oy = room["o"]
    calx, caly = room["cal"]
    base_x, base_y = iso_xy(ox, oy)

    def to_local(px: float, py: float) -> tuple[float, float]:
        wx = px - calx + base_x
        wy = py - caly + base_y
        a = wx / (TW / 2)
        b = wy / (TH / 2)
        return (b + a) / 2 - ox, (b - a) / 2 - oy

    return to_local


def tile_center_px(room: dict, i: float, j: float) -> tuple[int, int]:
    """Room-local tile (i,j) center → image pixel (floor plane)."""
    ox, oy = room["o"]
    calx, caly = room["cal"]
    wx, wy = iso_xy(ox + i + 0.5, oy + j + 0.5)
    bx, by = iso_xy(ox, oy)
    return int(wx - bx + calx), int(wy - by + caly)


def near(c: tuple[int, int, int], palette: list[tuple[int, int, int]], tol: int) -> bool:
    return any(
        abs(c[0] - p[0]) <= tol and abs(c[1] - p[1]) <= tol and abs(c[2] - p[2]) <= tol
        for p in palette
    )


# ── Extraction ────────────────────────────────────────────────────────


def sample_floor_palette(px, w: int, h: int, room: dict) -> list[tuple[int, int, int]]:
    """Floor colors from the open south tip of the floor (never furniture).

    The disc around a tile near the S tip is open floor in every room of
    this set. Must be paired with the ARCHIVE art (see ARCHIVE_ROOMS) —
    that is the art the shipped footprints were validated against.
    """
    rw, rh = room["s"]
    sx, sy = tile_center_px(room, rw / 2 - 0.5, rh - 0.5)
    buckets: dict[tuple[int, int, int], int] = {}
    samples = 0
    R = 56
    for y in range(max(0, sy - R), min(h, sy + R)):
        for x in range(max(0, sx - R), min(w, sx + R)):
            if (x - sx) ** 2 + (y - sy) ** 2 > R * R:
                continue
            r, g, b, a = px[y][x]
            if a < 200:
                continue
            buckets[(r // 12, g // 12, b // 12)] = (
                buckets.get((r // 12, g // 12, b // 12), 0) + 1
            )
            samples += 1
    # Keep buckets covering ~85% of samples (tolerant of rug/label edges)
    out: list[tuple[int, int, int]] = []
    covered = 0
    for (r, g, b), n in sorted(buckets.items(), key=lambda kv: -kv[1]):
        out.append((r * 12 + 6, g * 12 + 6, b * 12 + 6))
        covered += n
        if covered >= samples * 0.85:
            break
    return out


def wall_region_tester(room: dict):
    """Excludes wall pixels from the furniture test.

    Walls are two parallelograms in image space: back wall along the room's
    top edge (local y = -1 row) and left wall along the left edge (local
    x = -1 column), each WALL_H tall. Any sample inside them is wall art,
    not furniture — bookshelves in front of the wall poke INTO the room
    below the wall base, which is exactly what we want to keep.
    """
    ox, oy = room["o"]
    rw, rh = room["s"]
    P1 = iso_xy(ox - 1, oy - 1)          # corner where both walls meet
    P2 = iso_xy(ox + rw, oy - 1)         # back wall far end
    P3 = iso_xy(ox - 1, oy + rh)         # left wall far end
    H = 150  # taller than any wall art post-warp; only the room interior matters

    def inside(p: tuple[float, float], A: tuple[float, float], B: tuple[float, float]) -> bool:
        # Parallelogram A→B spanned vertically by H.
        ux, uy = B[0] - A[0], B[1] - A[1]
        ulen2 = ux * ux + uy * uy
        if ulen2 == 0:
            return False
        t = ((p[0] - A[0]) * ux + (p[1] - A[1]) * uy) / ulen2
        if t < 0 or t > 1:
            return False
        # projection point on base line; vertical distance above it
        bx, by = A[0] + t * ux, A[1] + t * uy
        return 0 <= by - p[1] <= H

    def is_wall(px_: float, py_: float) -> bool:
        return inside((px_, py_), P1, P2) or inside((px_, py_), P1, P3)

    return is_wall


def extract(room_id: str, cover: float = 0.55) -> list[list[float]]:
    """Per-tile footprint extraction from the ARCHIVE (pre-warp) art.

    straighten_and_grow warps each room with a lattice-locked affine and
    grows it by whole-tile cloning of open floor — so a furniture blob at
    local tile (i,j) in the archive art sits at the SAME (i,j) after the
    warp, and the grown bands are walkable everywhere. Extracting here
    therefore yields the same footprints as extracting from the shipped
    (warped/grown) art, but against the art the classifier was tuned on.
    """
    """Per-tile footprint extraction via TWO robust tests.

    For each tile, sample a pixel column through its floor plane
    (dx across the tile, dy from -34 to +4 relative to the plane):

    1. OCCLUDED FLOOR: the bottom band (dy -6..+4, the tile's own floor
       diamond) is mostly NOT floor-colored → something stands on the
       tile itself. Rugs/decals are floor-colored → walkable. This is the
       primary test and is what catches the conference table, whose sprite
       covers the floor all the way down.
    2. TALL BULK: the mid band (dy -34..-8) is mostly non-floor AND the
       colors span a wide vertical range (median brightness varies > 18)
       → a tall object overhangs this tile. The spread requirement keeps
       flat-but-dark floor (shadows, dark rugs) walkable.

    Wall/back-wall pixels and background are excluded before testing.
    """
    room = ARCHIVE_ROOMS[room_id]
    rw, rh = int(room["s"][0]), int(room["s"][1])
    w, h, px = read_png(ARC / f"{room_id}.png")

    floor = sample_floor_palette(px, w, h, room)
    base_floor = list(floor)
    for k in (0.85, 0.7, 0.55, 0.45):
        floor += [(int(r * k), int(g * k), int(b * k)) for r, g, b in base_floor]

    is_wall = wall_region_tester(room)

    DXS = (-20, -10, 0, 10, 20)
    BOTTOM_DYS = (-6, -2, 2)
    MID_DYS = tuple(range(-34, -6, 4))

    def non_floor(x: int, y: int) -> bool:
        r, g, b, a = px[y][x]
        if a < 40:
            return False
        if is_wall(x, y):
            return False
        if abs(r - BG[0]) < 14 and abs(g - BG[1]) < 14 and abs(b - BG[2]) < 14:
            return False
        if near((r, g, b), floor, 20):
            return False
        return True

    def column(cx: int, cy: int, dys) -> tuple[int, int, list[int]]:
        hits = 0
        total = 0
        lum: list[int] = []
        for dx in DXS:
            for dy in dys:
                x, y = cx + dx, cy + dy
                if 0 <= x < w and 0 <= y < h:
                    total += 1
                    r, g, b, a = px[y][x]
                    lum.append((r + g + b) // 3)
                    if non_floor(x, y):
                        hits += 1
        return hits, total, lum

    def tile_blocked(i: int, j: int) -> bool:
        cx, cy = tile_center_px(room, i, j)
        b_hits, b_total, _ = column(cx, cy, BOTTOM_DYS)
        if b_total > 0 and b_hits / b_total > 0.55:
            return True  # floor occluded: something stands here
        m_hits, m_total, m_lum = column(cx, cy, MID_DYS)
        if m_total == 0:
            return False
        spread = max(m_lum) - min(m_lum) if m_lum else 0
        if m_hits / m_total > cover and spread > 18:
            return True  # tall bulk with vertical structure
        return False

    blocked = [[tile_blocked(i, j) for i in range(rw)] for j in range(rh)]

    # Anchor tiles stay walkable (people stand/sit exactly there).
    unblock_catalog_chairs(room_id, blocked)

    # Merge horizontal runs per row
    rects: list[list[float]] = []
    for j in range(rh):
        i = 0
        while i < rw:
            if not blocked[j][i]:
                i += 1
                continue
            i0 = i
            while i < rw and blocked[j][i]:
                i += 1
            rects.append([float(i0), float(j), float(i - i0), 1.0])

    # Merge vertically identical runs (same i0/width in consecutive rows)
    merged: list[list[float]] = []
    for r in sorted(rects, key=lambda r: (r[0], r[1])):
        hit = None
        for m in merged:
            if m[0] == r[0] and m[2] == r[2] and abs(m[1] + m[3] - r[1]) < 0.01:
                hit = m
                break
        if hit:
            hit[3] += r[3]
        else:
            merged.append(list(r))

    return merged


def unblock_catalog_chairs(room_id: str, blocked: list[list[bool]]) -> None:
    """Anchor tiles from EmployeeCatalog RAW_EMPLOYEES stay walkable.

    Only the anchor tile itself (people stand/sit exactly there), NOT a
    3x3 neighborhood — a wide unblock used to swallow the desk footprint
    next to the chair and let people clip through it.
    """
    room = ROOMS[room_id]
    ox, oy = room["o"]
    for _id, _name, _role, _team, _agent, rid, (gx, gy), _f in EMPLOYEES:
        if rid != room_id:
            continue
        li = int(round(gx - ox))
        lj = int(round(gy - oy))
        if 0 <= li < len(blocked[0]) and 0 <= lj < len(blocked):
            blocked[lj][li] = False


# Imported late to avoid a cycle with the app bundle.
from employee_catalog_data import EMPLOYEES  # noqa: E402


def main() -> int:
    for room_id in ROOMS:
        rects = extract(room_id)
        print(f"// {room_id} — {len(rects)} footprints")
        for r in rects:
            print(f"      [{r[0]}, {r[1]}, {r[2]}, {r[3]}],")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
