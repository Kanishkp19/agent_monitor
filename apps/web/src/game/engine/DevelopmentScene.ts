import { buildNavGrid, findPath } from './NavGrid'
import { iso } from './IsoMath'

export interface Point { x: number; y: number }
export interface Desk extends Point { id: string; w: number; d: number; seat: Point }

/** Original vector kit: 2:1 projection, 64×32 tile, 48px person, 24px desk,
 * 72px rear walls, upper-left lighting. Feet and seats use tile coordinates.
 * Geometry, navigation and rendering all consume this definition. */
export const DEVELOPMENT = {
  width: 14, height: 11,
  room: { x: 0, y: 0, w: 11, d: 11 },
  door: { x: 11, y: 8 },
  spawn: { x: 12, y: 9 },
  breakPoint: { x: 12, y: 2 },
  plants: [{ x: .7, y: 9.3 }, { x: 9.6, y: .8 }],
  counter: { x: 12.3, y: .5, w: .9, d: .9 },
  walls: [[11, 0, 1, 8], [11, 9, 1, 2]] as [number, number, number, number][],
  desks: [
    { id: 'a1', x: 2, y: 3, w: 2, d: 1, seat: { x: 3, y: 2 } },
    { id: 'a2', x: 6, y: 3, w: 2, d: 1, seat: { x: 7, y: 2 } },
    { id: 'b1', x: 2, y: 7, w: 2, d: 1, seat: { x: 3, y: 6 } },
    { id: 'b2', x: 6, y: 7, w: 2, d: 1, seat: { x: 7, y: 6 } },
  ] satisfies Desk[],
}

export function developmentNav() {
  return buildNavGrid(DEVELOPMENT.width, DEVELOPMENT.height, [
    ...DEVELOPMENT.walls,
    ...DEVELOPMENT.plants.map((p): [number, number, number, number] => [p.x, p.y, .55, .55]),
    [DEVELOPMENT.counter.x, DEVELOPMENT.counter.y, DEVELOPMENT.counter.w, DEVELOPMENT.counter.d],
    ...DEVELOPMENT.desks.map((d): [number, number, number, number] => [d.x, d.y, d.w, d.d]),
  ])
}

/** One depth convention for feet and the front edge of solid furniture. */
export function sceneDepth(p: Point): number { return p.x + p.y }
export function deskDepth(d: Desk): number { return d.x + d.y + d.w + d.d }

export function unproject(x: number, y: number): Point {
  return { x: x / 64 + y / 32, y: y / 32 - x / 64 }
}

/** Deterministic route goes behind/in front of both clusters and through door. */
export function developmentTour(seat: Point): Point[] {
  const nav = developmentNav()
  const stops = [seat, { x: 1, y: 5 }, { x: 9, y: 9 }, DEVELOPMENT.breakPoint, seat]
  const result: Point[] = [seat]
  for (let i = 1; i < stops.length; i++) {
    const segment = findPath(nav, stops[i - 1]!, stops[i]!)
    if (!segment) throw new Error('Development scene has an unreachable interaction')
    result.push(...segment.slice(1))
  }
  return result
}

export function sampleTour(path: Point[], time: number): { position: Point; seated: boolean; phase: number } {
  const phase = time % (path.length - 1 + 7)
  if (phase < 7) return { position: path[0]!, seated: true, phase }
  const step = phase - 7
  const a = path[Math.floor(step)]!
  const b = path[Math.min(Math.floor(step) + 1, path.length - 1)]!
  const t = step % 1
  return { position: { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }, seated: false, phase }
}

export function projectedFoot(p: Point, seated: boolean): Point {
  const foot = iso(p.x, p.y)
  return { x: foot.x, y: foot.y - (seated ? 5 : 0) }
}
