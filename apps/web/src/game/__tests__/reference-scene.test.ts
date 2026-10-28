import { describe, expect, it } from 'vitest'
import { assignOfficeSeats, CATALOG_SEATS, EXTRA_SEATS, OFFICE_ROOMS, type OfficeSeat } from '../engine/ReferenceScene'

describe('reference office seating', () => {
  it('has a distinct in-room seat for all twenty catalog employees', () => {
    expect(CATALOG_SEATS.size).toBe(20)
    const keys = new Set<string>()
    for (const s of CATALOG_SEATS.values()) {
      const r = OFFICE_ROOMS.find((r) => r.id === s.room)!
      expect(s.x).toBeGreaterThan(r.x)
      expect(s.y).toBeGreaterThan(r.y)
      expect(s.x).toBeLessThan(r.x + r.w)
      expect(s.y).toBeLessThan(r.y + r.h)
      keys.add(`${s.x},${s.y}`)
    }
    expect(keys.size).toBe(20)
  })
  it('does not move existing employees when another disappears or reconnects', () => {
    const assigned = new Map<string, OfficeSeat>()
    assignOfficeSeats(['custom-b', 'custom-a', 'emp_004'], assigned)
    const a = assigned.get('custom-a'), b = assigned.get('custom-b')
    assignOfficeSeats(['custom-b', 'custom-c'], assigned)
    assignOfficeSeats(['custom-a'], assigned)
    expect(assigned.get('custom-a')).toEqual(a)
    expect(assigned.get('custom-b')).toEqual(b)
    expect(assigned.get('emp_004')).toEqual(CATALOG_SEATS.get('emp_004'))
    expect(new Set([...assigned.values()].map((s) => `${s.x},${s.y}`)).size).toBe(4)
  })
  it('never overlaps excess live employees with reserved desks', () => {
    const assigned = assignOfficeSeats(Array.from({ length: 10 }, (_, i) => `new-${i}`), new Map())
    expect(assigned.size).toBe(EXTRA_SEATS.length)
    for (const seat of assigned.values()) expect(EXTRA_SEATS).toContain(seat)
    assignOfficeSeats([...CATALOG_SEATS.keys()], assigned)
    expect(new Set([...assigned.values()].map((s) => `${s.x},${s.y}`)).size).toBe(24)
  })
})
