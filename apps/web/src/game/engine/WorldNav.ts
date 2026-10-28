/**
 * World navigation: one global nav grid across all five rooms.
 *
 * Built from Furniture rects (already translated to global tiles) plus the
 * room interiors from WorldRenderer's ROOMS. Everything outside a room
 * interior is solid — that's the wall/void layer. The grid coordinate
 * system IS the global tile coordinate system (origin 0,0), so callers
 * pass global tiles straight in with no offset math.
 *
 * Built once at boot; `navdebug` rendering lives here too.
 */

import { ROOMS } from './WorldRenderer'
import { furnitureFor } from './Furniture'
import type { NavGrid } from './NavGrid'
import { iso } from './IsoMath'

export interface WorldNav {
  grid: NavGrid
}

/** Build the world nav from room interiors + furniture footprints. */
export function buildWorldNav(): WorldNav {
  let maxX = -Infinity
  let maxY = -Infinity
  for (const r of ROOMS) {
    maxX = Math.max(maxX, r.o[0] + r.s[0])
    maxY = Math.max(maxY, r.o[1] + r.s[1])
  }

  const w = Math.ceil(maxX) + 1
  const h = Math.ceil(maxY) + 1
  const blocked = new Uint8Array(w * h).fill(1) // start solid, carve rooms

  // Carve room interiors.
  for (const r of ROOMS) {
    const x0 = Math.round(r.o[0])
    const y0 = Math.round(r.o[1])
    for (let y = y0; y < y0 + r.s[1]; y++) {
      for (let x = x0; x < x0 + r.s[0]; x++) {
        blocked[y * w + x] = 0
      }
    }
  }

  // Block furniture rects (already global via furnitureFor).
  for (const r of ROOMS) {
    const f = furnitureFor(r.id)
    for (const [rx, ry, rw, rd] of f.rects) {
      const x0 = Math.max(0, Math.floor(rx))
      const y0 = Math.max(0, Math.floor(ry))
      const x1 = Math.min(w - 1, Math.ceil(rx + rw) - 1)
      const y1 = Math.min(h - 1, Math.ceil(ry + rd) - 1)
      for (let y = y0; y <= y1; y++) {
        for (let x = x0; x <= x1; x++) {
          blocked[y * w + x] = 1
        }
      }
    }
  }

  return { grid: { w, h, blocked } }
}

/**
 * Draw the nav overlay (debug): furniture tiles get a red wash, POIs get
 * green markers. Cheap enough to run every frame while calibrating.
 */
export function drawNavDebug(c: CanvasRenderingContext2D, nav: WorldNav): void {
  const { grid } = nav
  c.save()
  for (let y = 0; y < grid.h; y++) {
    for (let x = 0; x < grid.w; x++) {
      if (grid.blocked[y * grid.w + x] !== 1) continue
      // Only draw blocked tiles inside a room (furniture), not the void
      // between rooms — the void would cover the whole canvas.
      if (!insideAnyRoom(x + 0.5, y + 0.5)) continue
      const p = iso(x, y)
      c.fillStyle = 'rgba(229,72,77,0.35)'
      c.beginPath()
      c.moveTo(p.x, p.y - 16)
      c.lineTo(p.x + 32, p.y)
      c.lineTo(p.x, p.y + 16)
      c.lineTo(p.x - 32, p.y)
      c.closePath()
      c.fill()
    }
  }
  // POI markers
  for (const r of ROOMS) {
    const f = furnitureFor(r.id)
    for (const [bx, by] of [...f.breaks, ...f.strolls]) {
      const p = iso(bx, by)
      c.fillStyle = '#3FCF8E'
      c.beginPath()
      c.arc(p.x, p.y, 3.5, 0, Math.PI * 2)
      c.fill()
    }
  }
  c.restore()
}

function insideAnyRoom(x: number, y: number): boolean {
  for (const r of ROOMS) {
    if (x >= r.o[0] && x < r.o[0] + r.s[0] && y >= r.o[1] && y < r.o[1] + r.s[1]) return true
  }
  return false
}
