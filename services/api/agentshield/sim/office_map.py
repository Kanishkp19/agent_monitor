"""The floor plan, server-side.

The renderer draws rooms and desks from
`apps/web/public/assets/office/office-map.json`, but the *assignment* of
employees to desks happens here at seed time, because rehydration depends on
it: if the office decided where people sat, a page reload would reshuffle the
floor and the snapshot would be fiction.

`desks[].slot` is the contract between the two. `seed.py` writes
`emp_007 -> dev_floor/d04`; the renderer looks up the slot and gets both the
tile and the facing.

Five rooms as separate floating islands, which is an engineering choice as
much as an aesthetic one: no doors, no corridors, no inter-room pathfinding
and no occlusion. Characters never leave their room, so the hardest part of
isometric rendering does not arise.
"""

from __future__ import annotations

from typing import Any

TILE_W = 64
TILE_H = 32
MAP_W = 48
MAP_H = 40

ROOMS: dict[str, dict[str, Any]] = {
    "ceo_office": {
        "label": "CEO OFFICE",
        "origin": (2, 2),
        "size": (10, 8),
        "floor_tile": "floor_wood",
        "label_anchor": (7, 5),
        "desks": {"c01": {"at": (5, 5), "facing": "e"}},
    },
    "managers": {
        "label": "MANAGERS",
        "origin": (16, 1),
        "size": (12, 7),
        "floor_tile": "floor_carpet_red",
        "label_anchor": (22, 4),
        "desks": {
            "m01": {"at": (19, 3), "facing": "e"},
            "m02": {"at": (23, 3), "facing": "e"},
            "m03": {"at": (19, 6), "facing": "e"},
        },
    },
    "dev_floor": {
        "label": "DEVELOPMENT FLOOR",
        "origin": (26, 5),
        "size": (20, 22),
        "floor_tile": "floor_grey",
        "label_anchor": (36, 14),
        "desks": {
            "d01": {"at": (28, 8), "facing": "e"},
            "d02": {"at": (31, 8), "facing": "e"},
            "d03": {"at": (34, 8), "facing": "e"},
            "d04": {"at": (37, 8), "facing": "e"},
            "d05": {"at": (40, 8), "facing": "e"},
            "d06": {"at": (28, 12), "facing": "e"},
            "d07": {"at": (31, 12), "facing": "e"},
            "d08": {"at": (34, 12), "facing": "e"},
            "d09": {"at": (37, 12), "facing": "e"},
            "d10": {"at": (40, 12), "facing": "e"},
            "d11": {"at": (28, 16), "facing": "e"},
            "d12": {"at": (31, 16), "facing": "e"},
            "d13": {"at": (34, 16), "facing": "e"},
            "d14": {"at": (37, 16), "facing": "e"},
            "d15": {"at": (40, 16), "facing": "e"},
            "d16": {"at": (28, 20), "facing": "e"},
            "d17": {"at": (31, 20), "facing": "e"},
            "d18": {"at": (34, 20), "facing": "e"},
        },
    },
    "devops": {
        "label": "DEVOPS",
        "origin": (1, 13),
        "size": (11, 8),
        "floor_tile": "floor_grey",
        "label_anchor": (6, 16),
        "desks": {
            "o01": {"at": (4, 16), "facing": "e"},
            "o02": {"at": (8, 16), "facing": "e"},
        },
    },
    "meeting_room": {
        "label": "MEETING ROOM",
        "origin": (5, 24),
        "size": (16, 12),
        "floor_tile": "floor_carpet_red",
        "label_anchor": (13, 29),
        # No fixed desks -- meetings are transient and cosmetic.
        "desks": {},
    },
}


def desk_for_slot(room: str, slot: str) -> tuple[int, int]:
    """Tile coordinates for a desk slot.

    Falls back to the room origin rather than raising: a missing desk should
    put someone in the wrong corner, not stop a run from seeding.
    """
    definition = ROOMS.get(room)
    if not definition:
        return (0, 0)
    desk = definition["desks"].get(slot)
    if not desk:
        return tuple(definition["origin"])  # type: ignore[return-value]
    return tuple(desk["at"])  # type: ignore[return-value]


def facing_for_slot(room: str, slot: str) -> str:
    definition = ROOMS.get(room)
    if not definition:
        return "s"
    desk = definition["desks"].get(slot)
    return str(desk["facing"]) if desk else "s"


def room_of(slot_path: str) -> str:
    """`dev_floor/d04` -> `dev_floor`."""
    return slot_path.split("/", 1)[0] if "/" in slot_path else slot_path


def tile_to_world(tx: int, ty: int) -> tuple[float, float]:
    """Standard 2:1 isometric projection. Mirrors the client's `tileToWorld`."""
    return ((tx - ty) * (TILE_W / 2), (tx + ty) * (TILE_H / 2))


def depth_for(tx: int, ty: int, layer: int = 0) -> int:
    """The only correct depth rule for 2:1 iso with tall sprites.

    Depth from `(tx + ty)`, never from world `y` -- getting this wrong renders
    characters behind the desks they are sitting at.
    """
    return (tx + ty) * 10 + layer
