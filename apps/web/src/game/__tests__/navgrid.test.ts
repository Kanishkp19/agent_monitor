import { describe, expect, it } from 'vitest'

import {
  buildNavGrid,
  isBlocked,
  isWalkable,
  nearestWalkable,
  findPath,
  smooth,
  route,
} from '../engine/NavGrid'

/**
 * The nav grid is the anti-sloppiness guarantee: nobody walks through a
 * desk because desks are solid *data*, not vibes. These tests pin the
 * grid semantics, A* optimality on small mazes, and the smoothing
 * contract (turn only where you must).
 */

function emptyGrid(w = 10, h = 10) {
  return buildNavGrid(w, h, [])
}

describe('buildNavGrid', () => {
  it('blocks exactly the rect tiles (floor-snapped)', () => {
    const g = buildNavGrid(10, 10, [
      [2, 2, 2, 1], // tiles (2,2) and (3,2)
    ])
    expect(isBlocked(g, 2, 2)).toBe(true)
    expect(isBlocked(g, 3, 2)).toBe(true)
    expect(isBlocked(g, 4, 2)).toBe(false)
    expect(isBlocked(g, 2, 3)).toBe(false)
  })

  it('clips rects that overhang the grid edge', () => {
    const g = buildNavGrid(5, 5, [[4, 4, 10, 10]])
    expect(isBlocked(g, 4, 4)).toBe(true)
    expect(isWalkable(g, 3, 3)).toBe(true)
    expect(isBlocked(g, 9, 9)).toBe(true) // out-of-bounds is solid
  })

  it('treats out-of-bounds as solid', () => {
    const g = emptyGrid()
    expect(isBlocked(g, -1, 0)).toBe(true)
    expect(isBlocked(g, 0, -1)).toBe(true)
    expect(isBlocked(g, 10, 5)).toBe(true)
    expect(isBlocked(g, 5, 10)).toBe(true)
  })
})

describe('nearestWalkable', () => {
  it('returns the tile itself when walkable', () => {
    const g = emptyGrid()
    expect(nearestWalkable(g, 4.6, 3.2)).toEqual({ x: 5, y: 3 })
  })

  it('finds the closest walkable ring around a solid pocket', () => {
    const g = buildNavGrid(7, 7, [[1, 1, 3, 3]])
    const spot = nearestWalkable(g, 2, 2)
    expect(spot).not.toBeNull()
    if (spot) {
      expect(isWalkable(g, spot.x, spot.y)).toBe(true)
      // Ring 1 around (2,2) is entirely inside the 3x3 pocket, so the
      // nearest walkable tile sits on ring 2.
      expect(Math.max(Math.abs(spot.x - 2), Math.abs(spot.y - 2))).toBe(2)
    }
  })
})

describe('findPath', () => {
  it('returns [start] when start equals goal', () => {
    const g = emptyGrid()
    expect(findPath(g, { x: 3, y: 3 }, { x: 3, y: 3 })).toEqual([{ x: 3, y: 3 }])
  })

  it('finds the optimal L-shaped route around furniture', () => {
    // Wall with a gap at y=5
    const g = buildNavGrid(9, 9, [[4, 0, 1, 5]])
    const path = findPath(g, { x: 2, y: 2 }, { x: 6, y: 2 })
    expect(path).not.toBeNull()
    if (!path) return
    // Detour: 3 down, 4 across, 3 up = 10 moves = 11 tiles.
    expect(path.length).toBe(11)
    const wallX = path.filter((p) => p.x === 4)
    expect(wallX.every((p) => p.y >= 5)).toBe(true)
  })

  it('returns null when the goal is unreachable', () => {
    const g = buildNavGrid(9, 9, [
      [0, 0, 9, 4], // sealed top half
      [0, 5, 9, 4], // sealed bottom half (gap col 4 rows 4 only)
    ])
    // (4,4) is the only walkable tile between the halves
    const path = findPath(g, { x: 2, y: 2 }, { x: 2, y: 7 })
    expect(path).toBeNull()
  })

  it('returns null when start or goal is inside furniture', () => {
    const g = buildNavGrid(9, 9, [[4, 4, 2, 2]])
    expect(findPath(g, { x: 4, y: 4 }, { x: 0, y: 0 })).toBeNull()
    expect(findPath(g, { x: 0, y: 0 }, { x: 5, y: 5 })).toBeNull()
  })
})

describe('smooth', () => {
  it('collapses collinear runs and keeps corners', () => {
    const path = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 1 },
      { x: 3, y: 2 },
    ]
    const s = smooth(path)
    expect(s).toEqual([
      { x: 0, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 2 },
    ])
  })

  it('keeps paths of length <= 2 untouched', () => {
    const path = [{ x: 1, y: 1 }, { x: 2, y: 1 }]
    expect(smooth(path)).toEqual(path)
  })
})

describe('route', () => {
  it('produces tile-center waypoints starting ahead of the walker', () => {
    const g = emptyGrid(12, 12)
    const waypoints = route(g, 2.1, 2.1, 6, 6)
    expect(waypoints).not.toBeNull()
    if (!waypoints) return
    expect(waypoints.length).toBeGreaterThan(0)
    // First waypoint is NOT the tile we're standing in
    expect(waypoints[0]).not.toEqual({ tx: 2, ty: 2 })
    // Ends at the goal tile
    const last = waypoints[waypoints.length - 1]!
    expect(last).toEqual({ tx: 6, ty: 6 })
    // Every waypoint is walkable
    for (const wp of waypoints) {
      expect(isWalkable(g, wp.tx, wp.ty)).toBe(true)
    }
  })

  it('routes around desks (furniture integrity)', () => {
    const g = buildNavGrid(12, 12, [[4, 4, 2, 2]]) // a desk block
    const waypoints = route(g, 2, 5, 8, 5)
    expect(waypoints).not.toBeNull()
    if (!waypoints) return
    for (const wp of waypoints) {
      expect(isWalkable(g, wp.tx, wp.ty)).toBe(true)
    }
    // No waypoint inside the desk footprint
    for (const wp of waypoints) {
      expect(wp.tx >= 4 && wp.tx <= 5 && wp.ty >= 4 && wp.ty <= 5).toBe(false)
    }
  })
})
