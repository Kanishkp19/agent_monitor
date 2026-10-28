import { describe, expect, it } from 'vitest'
import { iso } from '../engine/IsoMath'
import { findPath, isWalkable } from '../engine/NavGrid'
import { DEVELOPMENT, deskDepth, developmentNav, developmentTour, sampleTour, sceneDepth, unproject } from '../engine/DevelopmentScene'

describe('development floor geometry', () => {
  it('connects every seat to the corridor through the explicit doorway', () => {
    const nav = developmentNav()
    for (const desk of DEVELOPMENT.desks) {
      expect(isWalkable(nav, desk.seat.x, desk.seat.y)).toBe(true)
      const path = findPath(nav, DEVELOPMENT.spawn, desk.seat)
      expect(path).not.toBeNull()
      expect(path).toContainEqual(DEVELOPMENT.door)
    }
  })

  it('keeps the complete tour outside furniture and the partition', () => {
    const nav = developmentNav()
    const path = developmentTour(DEVELOPMENT.desks[0]!.seat)
    expect(path).toContainEqual(DEVELOPMENT.breakPoint)
    expect(path).toContainEqual(DEVELOPMENT.door)
    for (const p of path) expect(isWalkable(nav, p.x, p.y)).toBe(true)
    for (let i = 1; i < path.length; i++) {
      expect(Math.abs(path[i]!.x - path[i - 1]!.x) + Math.abs(path[i]!.y - path[i - 1]!.y)).toBe(1)
    }
  })

  it('orders seated people behind tabletops and people in the front aisle above them', () => {
    for (const desk of DEVELOPMENT.desks) {
      expect(sceneDepth(desk.seat)).toBeLessThan(deskDepth(desk))
      expect(sceneDepth({ x: desk.x + desk.w, y: desk.y + desk.d + 1 })).toBeGreaterThan(deskDepth(desk))
    }
  })

  it('round trips projection for hit testing, including negative screen x', () => {
    for (const point of [DEVELOPMENT.door, DEVELOPMENT.spawn, { x: 1.5, y: 8.25 }]) {
      const screen = iso(point.x, point.y)
      expect(unproject(screen.x, screen.y)).toEqual(point)
    }
  })

  it('transitions from seated to walking and returns without a position jump', () => {
    const path = developmentTour(DEVELOPMENT.desks[0]!.seat)
    expect(sampleTour(path, 6.99).seated).toBe(true)
    expect(sampleTour(path, 7).seated).toBe(false)
    expect(sampleTour(path, 7).position).toEqual(path[0])
    expect(sampleTour(path, path.length - 1 + 7).position).toEqual(path[0])
    const half = sampleTour(path, 7.5).position
    expect(half.x).toBe((path[0]!.x + path[1]!.x) / 2)
    expect(half.y).toBe((path[0]!.y + path[1]!.y) / 2)
  })
})
