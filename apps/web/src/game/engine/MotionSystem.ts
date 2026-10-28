/**
 * Motion system: dt-based path following over the nav grid.
 *
 * Movement is *distance-synced*: the walk cycle phase advances with the
 * distance actually covered, so feet plant exactly when frames show a
 * planted foot — no moonwalking at any speed. Facing comes from the
 * dominant axis of the current segment, which matches the 4-way atlas.
 *
 * Everything is driven by an explicit dt (scaled by the sim speed), so
 * pausing the simulation (speed 0) freezes people mid-stride instead of
 * letting RAF-time keep flowing.
 */

import { iso } from './IsoMath'
import { route, type NavGrid } from './NavGrid'
import type { SimEmployee } from '../systems/Types'

export const WALK_SPEED = 2.3 // tiles per second at speed multiplier 1

/**
 * One frame of motion. `dt` is simulation seconds (already multiplied by
 * the global speed). Speed 0 must be passed as dt 0 — people freeze.
 */
export function updateMotion(employees: SimEmployee[], nav: NavGrid | undefined, dt: number): void {
  for (const e of employees) {
    tickEmployee(e, nav, dt)
  }
}

function tickEmployee(e: SimEmployee, nav: NavGrid | undefined, dt: number): void {
  // Straight-line micro movement (sit/stand) — not path based.
  // `m.start` doubles as the elapsed-time accumulator (ms, sim-scaled).
  if (e.moving) {
    const m = e.moving
    m.start += dt * 1000
    const k = Math.min(1, m.start / m.dur)
    const s = k < 0.5 ? 2 * k * k : -1 + (4 - 2 * k) * k
    e.pos.x = m.fromX + (m.toX - m.fromX) * s
    e.pos.y = m.fromY + (m.toY - m.fromY) * s
    if (k >= 1) {
      const cb = m.after
      e.moving = null
      if (cb) cb()
    }
    return
  }

  // Path following
  if (e.path && nav) {
    const move = e.path
    let budget = move.speed * dt // tiles we may travel this frame

    while (budget > 0 && move.path.length > 0) {
      const wp = move.path[0]!
      const dx = wp.tx - e.pos.x
      const dy = wp.ty - e.pos.y
      const dist = Math.hypot(dx, dy)

      if (dist <= budget) {
        // Reach the waypoint, continue with leftover budget
        e.pos.x = wp.tx
        e.pos.y = wp.ty
        e.stride = (e.stride + dist / 0.62) % 1
        budget -= dist
        move.path.shift()
        if (move.path.length === 0) {
          const cb = move.after
          e.path = null
          e.activity = e.homeActivity === 'desk' ? 'stand' : e.homeActivity
          if (cb) cb()
          break
        }
      } else {
        // Partial step toward the waypoint
        e.pos.x += (dx / dist) * budget
        e.pos.y += (dy / dist) * budget
        e.stride = (e.stride + budget / 0.62) % 1 // 0.62 tiles ≈ one full stride
        budget = 0
      }
      // Facing from the segment we just advanced along
      if (dist > 1e-6) {
        setFacing(e, dx, dy)
      }
    }

    if (e.path) {
      e.animKind = 'walk'
      e.activity = 'walk'
    }
    return
  }

  // Not moving: decouple the idle/typing phase from wall time by dt.
  e.animPhase += dt * (e.activity === 'desk' ? 6.2 : 2.1)
}

/** Facing from a direction vector — dominant axis wins (matches the atlas). */
export function setFacing(e: SimEmployee, dx: number, dy: number): void {
  if (Math.abs(dx) > Math.abs(dy)) {
    e.facing = dx > 0 ? 'e' : 'w'
  } else if (Math.abs(dy) > 0.0001) {
    e.facing = dy > 0 ? 's' : 'n'
  }
}

/** Order a navigated walk. Falls back to a no-op stand if unreachable. */
export function walkPath(
  e: SimEmployee,
  nav: NavGrid | undefined,
  tx: number,
  ty: number,
  after?: () => void,
): void {
  e.moving = null
  if (!nav) {
    e.path = { path: [{ tx, ty }], speed: WALK_SPEED, after }
    return
  }
  const waypoints = route(nav, e.pos.x, e.pos.y, tx, ty)
  if (!waypoints || waypoints.length === 0) {
    // Unreachable: stand down rather than clip through walls.
    e.path = null
    e.activity = e.homeActivity
    after?.()
    return
  }
  e.path = { path: waypoints, speed: WALK_SPEED, after }
}

/** Cancel any movement (used when the governance FSM overrides the body). */
export function stopWalking(e: SimEmployee, snapTo = false): void {
  e.path = null
  e.moving = null
  if (snapTo) {
    e.pos.x = Math.round(e.pos.x)
    e.pos.y = Math.round(e.pos.y)
  }
}

/** Screen position of a person's feet (world space). */
export function feetScreen(wx: number, wy: number): { x: number; y: number } {
  return iso(wx, wy)
}
