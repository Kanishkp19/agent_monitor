import { describe, expect, it } from 'vitest'
import { animateOfficePerson } from '../engine/OfficeLife'
import { CATALOG_SEATS, OFFICE_ROOMS, type OfficePerson } from '../engine/ReferenceScene'
const people = [...CATALOG_SEATS].map(([id, seat]): OfficePerson => ({ ...seat, id, name: id, role: 'Engineer', state: 'idle', risk: false, live: true }))
describe('office life', () => {
  it('walks continuous loops within each room and behind the desk partitions', () => {
    for (const p of people) {
      const r = OFFICE_ROOMS.find((r) => r.id === p.room)!
      let previous = animateOfficePerson(p, 0, true, 0)
      let moved = false
      for (let t = .1; t < 72; t += .1) {
        const a = animateOfficePerson(p, t, true, 0)
        expect(a.x).toBeGreaterThan(r.x)
        expect(a.x).toBeLessThan(r.x + r.w)
        expect(a.y).toBeGreaterThan(r.y)
        expect(a.y).toBeLessThanOrEqual(p.y)
        expect(Math.hypot(a.x - previous.x, a.y - previous.y)).toBeLessThan(.1)
        moved ||= a.walking && a.x !== p.x
        expect(a.state).toBe('idle')
        previous = a
      }
      expect(moved).toBe(true)
    }
  })
  it('keeps working, waiting and blocked employees at their desks', () => {
    for (const state of ['working', 'waiting', 'blocked']) for (let t = 0; t < 36; t++) {
      const p = { ...people[0]!, state }, a = animateOfficePerson(p, t, true, 0)
      expect([a.x, a.y, a.walking]).toEqual([p.x, p.y, false])
    }
  })
  it('disables roaming for reduced motion and produces repeatable paused poses', () => {
    const p = people[0]!
    expect(animateOfficePerson(p, 5, false, 0).walking).toBe(false)
    expect(animateOfficePerson(p, 5, true, 0)).toEqual(animateOfficePerson(p, 5, true, 0))
    expect(animateOfficePerson(p, 5, true, 7).wave).toBe(true)
    expect(animateOfficePerson(p, 7, true, 7).wave).toBe(false)
    expect(p).not.toHaveProperty('phase')
  })
})
