/**
 * Furniture footprints and points of interest, per room.
 *
 * The room *art* is pre-rendered (see WorldRenderer); this module is the
 * machine-readable twin of that art: which tiles are solid, and where the
 * interesting standing spots are. NavGrid consumes the rects; the behavior
 * system consumes the POIs. No movement or behavior code hardcodes a
 * coordinate — change the art, change this table.
 *
 * Rects are stored in room-LOCAL tile coordinates [x, y, w, d] (fractions
 * allowed) and translated to global tiles by `furnitureFor`. Local (0,0) is
 * the room's walkable north-corner tile; walls sit at local x = -1 (left)
 * and y = -1 (back) and are solid by construction (the world nav blocks
 * everything outside room interiors).
 *
 * Invariant: a desk rect NEVER covers its chair tile — chairs are derived
 * from each employee's catalog `at` + `facing` (desk sits on the facing
 * side). That's what lets people stand at their desk and path home again.
 *
 * Calibration: toggle the `navdebug` overlay in OfficeSimulation (press `n`)
 * and tune rects until the red footprints hug the painted furniture.
 */

import { ROOMS } from './WorldRenderer'
import { EXTRACTED_FOOTPRINTS } from './footprints.generated'

export interface RoomFurniture {
  /** Solid furniture footprints [x, y, w, d] in local tiles. */
  rects: [number, number, number, number][]
  /** Standing spots for coffee/water/rack breaks. */
  breaks: [number, number][]
  /** Ambient stroll targets for idle/waiting wander. */
  strolls: [number, number][]
}

/* ── meeting room: conference table, 4 seated places ────────────── */
// Seats are calibrated against the table art in the MEETING_SEATS map
// (BehaviorSystem): front pair sits north of the table facing s, back pair
// sits south of the table facing n.

export const FURNITURE: Record<string, RoomFurniture> = {
  dev_floor: {
    rects: EXTRACTED_FOOTPRINTS.dev_floor ?? [],
    breaks: [
      [16.8, 15.4], // in front of the coffee machine
      [17.0, 9.4], // printer nook
      [2.6, 17.4], // lounge shelf
    ],
    strolls: [
      [13.4, 6.2],
      [9.4, 11.2],
      [5.4, 16.2],
      [14.2, 15.4],
      [10.4, 5.8],
    ],
  },

  managers: {
    rects: EXTRACTED_FOOTPRINTS.managers ?? [],
    breaks: [
      [10.2, 3.2], // printer corner
      [5.4, 2.0], // open floor between desk and shelves
    ],
    strolls: [
      [10.0, 4.4],
      [5.4, 3.2],
      [5.0, 6.2],
    ],
  },

  ceo_office: {
    rects: EXTRACTED_FOOTPRINTS.ceo_office ?? [],
    breaks: [
      [7.0, 1.4], // window spot
      [2.2, 4.6], // by the plant
    ],
    strolls: [
      [7.4, 2.2],
      [2.4, 3.4],
      [6.4, 5.6],
    ],
  },

  devops: {
    rects: EXTRACTED_FOOTPRINTS.devops ?? [],
    breaks: [
      [7.4, 2.8], // by the cabinet
      [1.8, 7.0], // racks end
    ],
    strolls: [
      [4.2, 4.4],
      [2.2, 6.4],
      [7.0, 6.6],
    ],
  },

  meeting_room: {
    rects: EXTRACTED_FOOTPRINTS.meeting_room ?? [],
    breaks: [
      [2.4, 6.0], // whiteboard
      [12.4, 6.2], // by the TV
    ],
    strolls: [
      [3.0, 9.0], // open floor south-west of the table
      [12.4, 8.6],
      [7.0, 10.2],
    ],
  },
}

/**
 * Accessor that tolerates a missing room (falls back to empty furniture).
 * Rects and POIs are translated to GLOBAL tile coordinates using the room
 * origins from WorldRenderer — callers (nav builder, behavior system) work
 * in global space because people do.
 */
export function furnitureFor(roomId: string): RoomFurniture {
  const room = ROOMS.find((r) => r.id === roomId)
  const f = FURNITURE[roomId]
  if (!room || !f) return { rects: [], breaks: [], strolls: [] }
  const [ox, oy] = room.o
  return {
    rects: f.rects.map(([x, y, w, d]) => [ox + x, oy + y, w, d] as [number, number, number, number]),
    breaks: f.breaks.map(([x, y]) => [ox + x, oy + y] as [number, number]),
    strolls: f.strolls.map(([x, y]) => [ox + x, oy + y] as [number, number]),
  }
}
