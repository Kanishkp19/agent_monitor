/**
 * Nav calibration view (dev only — `calibrate.html`).
 *
 * Draws the nav-relevant data directly over each room PNG at 1:1 pixels:
 * - cyan  : the tile grid (IsoMath projection with WorldRenderer calibration)
 * - yellow: wall exclusion regions used by the extractor
 * - red   : the footprints actually loaded by the nav (EXTRACTED_FOOTPRINTS)
 * - green : employee chair anchors (EmployeeCatalog positions)
 * - blue  : break/stroll POIs and meeting seats
 *
 * If red hugs the painted furniture and green/blue sit on open floor, the
 * nav is honest. Anything off → fix the extractor or the constants, not
 * the movement code.
 */

import { iso } from '../engine/IsoMath'
import { ROOMS } from '../engine/WorldRenderer'
import { FURNITURE, furnitureFor } from '../engine/Furniture'
import { RAW_EMPLOYEES } from '../engine/EmployeeCatalog'
import { MEETING_SEATS_EXPORT } from '../engine/BehaviorSystem'

const WALL_H = 62

/** Mirror of WorldRenderer CALIBRATION (kept literal to avoid import cycle). */
const CALIBRATION: Record<string, { dx: number; dy: number }> = {
  ceo_office: { dx: 424, dy: 172 },
  managers: { dx: 520, dy: 172 },
  dev_floor: { dx: 680, dy: 173 },
  devops: { dx: 487, dy: 172 },
  meeting_room: { dx: 423, dy: 173 },
}

const container = document.getElementById('rooms')!

for (const room of ROOMS) {
  const img = new Image()
  img.src = `/assets/office/rooms/${room.id}.png`
  await img.decode()

  const cv = document.createElement('canvas')
  cv.width = img.width
  cv.height = img.height
  const c = cv.getContext('2d')!
  c.drawImage(img, 0, 0)

  const [ox, oy] = room.o
  const base = iso(ox, oy)
  const cal = CALIBRATION[room.id] ?? { dx: 0, dy: 0 }
  const w2i = (wx: number, wy: number): [number, number] => [
    wx - base.x + cal.dx,
    wy - base.y + cal.dy,
  ]

  // ── tile grid ──
  c.strokeStyle = 'rgba(80,220,255,0.45)'
  c.lineWidth = 1
  for (let j = 0; j <= room.s[1]; j++) {
    for (let i = 0; i <= room.s[0]; i++) {
      const p = w2i(iso(ox + i, oy + j).x, iso(ox + i, oy + j).y)
      const q = w2i(iso(ox + i + 1, oy + j).x, iso(ox + i + 1, oy + j).y)
      const r = w2i(iso(ox + i + 1, oy + j + 1).x, iso(ox + i + 1, oy + j + 1).y)
      const s = w2i(iso(ox + i, oy + j + 1).x, iso(ox + i, oy + j + 1).y)
      c.beginPath()
      c.moveTo(p[0], p[1]); c.lineTo(q[0], q[1]); c.lineTo(r[0], r[1]); c.lineTo(s[0], s[1])
      c.closePath()
      c.stroke()
    }
  }

  // ── wall regions ──
  c.strokeStyle = 'rgba(255,220,60,0.85)'
  const [P1, P2, P3] = [
    w2i(iso(ox - 1, oy - 1).x, iso(ox - 1, oy - 1).y),
    w2i(iso(ox + room.s[0], oy - 1).x, iso(ox + room.s[0], oy - 1).y),
    w2i(iso(ox - 1, oy + room.s[1]).x, iso(ox - 1, oy + room.s[1]).y),
  ]
  for (const [A, B] of [
    [P1, P2],
    [P1, P3],
  ] as [[number, number], [number, number]][]) {
    c.beginPath()
    c.moveTo(A[0], A[1]); c.lineTo(B[0], B[1])
    c.lineTo(B[0], B[1] - WALL_H); c.lineTo(A[0], A[1] - WALL_H)
    c.closePath()
    c.stroke()
  }

  // ── footprints (what the nav blocks) ──
  const f = furnitureFor(room.id)
  for (const [x, y, w, d] of f.rects) {
    const P = w2i(iso(ox + x, oy + y).x, iso(ox + x, oy + y).y)
    const Q = w2i(iso(ox + x + w, oy + y).x, iso(ox + x + w, oy + y).y)
    const R = w2i(iso(ox + x + w, oy + y + d).x, iso(ox + x + w, oy + y + d).y)
    const S = w2i(iso(ox + x, oy + y + d).x, iso(ox + x, oy + y + d).y)
    c.beginPath()
    c.moveTo(P[0], P[1]); c.lineTo(Q[0], Q[1]); c.lineTo(R[0], R[1]); c.lineTo(S[0], S[1])
    c.closePath()
    c.fillStyle = 'rgba(229,72,77,0.4)'
    c.fill()
    c.strokeStyle = 'rgba(229,72,77,0.9)'
    c.stroke()
  }

  // ── employees (chair anchors) ──
  for (const [, , , , , rid, [gx, gy]] of RAW_EMPLOYEES) {
    if (rid !== room.id) continue
    const p = w2i(iso(gx, gy).x, iso(gx, gy).y)
    c.fillStyle = '#3FCF8E'
    c.beginPath(); c.arc(p[0], p[1], 5, 0, Math.PI * 2); c.fill()
  }

  // ── POIs + meeting seats ──
  c.fillStyle = '#4A90D9'
  for (const [bx, by] of [...f.breaks, ...f.strolls]) {
    const p = w2i(iso(bx, by).x, iso(bx, by).y)
    c.beginPath(); c.arc(p[0], p[1], 4, 0, Math.PI * 2); c.fill()
  }
  for (const [eid, sx, sy] of MEETING_SEATS_EXPORT) {
    void eid
    if (!roomLabel(room.id).includes('meeting')) continue
    const p = w2i(iso(sx, sy).x, iso(sx, sy).y)
    c.strokeStyle = '#4A90D9'
    c.lineWidth = 2
    c.beginPath(); c.arc(p[0], p[1], 7, 0, Math.PI * 2); c.stroke()
  }

  const cell = document.createElement('div')
  cell.className = 'cell'
  const h3 = document.createElement('h3')
  h3.textContent = `${room.id} (${FURNITURE[room.id]?.rects.length ?? 0} rects)`
  cell.append(h3, cv)
  container.append(cell)
}

function roomLabel(id: string): string {
  return id
}
