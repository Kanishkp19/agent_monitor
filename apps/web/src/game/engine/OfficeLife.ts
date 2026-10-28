import type { OfficePerson } from './ReferenceScene'

export interface AnimatedPerson extends OfficePerson { phase: number; walking: boolean; facingLeft: boolean; wave: boolean }
/** Short aisle loops behind each desk avoid its front and side partition.
 * Purely decorative: neither positions nor activities write to telemetry. */
export function animateOfficePerson(p: OfficePerson, time: number, roam: boolean, waveUntil: number): AnimatedPerson {
  const seed = [...p.id].reduce((n, c) => n + c.charCodeAt(0) * 7, 0)
  const phase = time * 5 + seed
  const canWalk = roam && ['idle', 'walking', 'offline'].includes(p.state)
  const cycle = (time + seed % 29) % (p.state === 'walking' ? 12 : 36)
  const walking = canWalk && cycle < 12
  let x = p.x, y = p.y, facingLeft = false
  if (walking) {
    const leg = Math.floor(cycle / 3), t = cycle % 3 / 3
    const length = p.room === 'ceo_office' ? 1.8 : p.room === 'devops' ? .8 : 1.1
    const points = [[0, 0], [0, -.7], [length, -.7], [0, -.7], [0, 0]]
    const a = points[leg]!, b = points[leg + 1]!
    x += a[0]! + (b[0]! - a[0]!) * t
    y += a[1]! + (b[1]! - a[1]!) * t
    facingLeft = leg === 2
  }
  return { ...p, x, y, phase, walking, facingLeft, wave: time < waveUntil }
}
