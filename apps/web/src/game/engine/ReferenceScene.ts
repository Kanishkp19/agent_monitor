import { box, iso, quad, drawWall, onWall } from './IsoMath'
import type { AnimatedPerson } from './OfficeLife'
import { RAW_EMPLOYEES, SHIRTS, SKINS, HAIRS } from './EmployeeCatalog'

export interface OfficeRoom { id: string; name: string; x: number; y: number; w: number; h: number; colors: [string, string] }
export const OFFICE_ROOMS: OfficeRoom[] = [
  { id: 'managers', name: 'MANAGERS', x: 0, y: 0, w: 8, h: 9, colors: ['#748391', '#7b8b98'] },
  { id: 'ceo_office', name: 'CEO OFFICE', x: 0, y: 9, w: 8, h: 11, colors: ['#beaa89', '#c8b595'] },
  { id: 'dev_floor', name: 'DEVELOPMENT FLOOR', x: 8, y: 0, w: 18, h: 12, colors: ['#cec6b2', '#c4bba6'] },
  { id: 'devops', name: 'DEVOPS', x: 8, y: 12, w: 6, h: 8, colors: ['#a89c89', '#b3a792'] },
  { id: 'meeting_room', name: 'MEETING ROOM', x: 14, y: 12, w: 12, h: 8, colors: ['#748493', '#7c8e9c'] },
]
export interface OfficeSeat { x: number; y: number; room: string }
const seats: OfficeSeat[] = [
  { x: 3.6, y: 13.2, room: 'ceo_office' },
  { x: 2.5, y: 3, room: 'managers' }, { x: 5.6, y: 3, room: 'managers' },
  ...Array.from({ length: 12 }, (_, i) => ({ x: 10 + i % 4 * 3.8, y: 2.5 + Math.floor(i / 4) * 3.5, room: 'dev_floor' })),
  { x: 10.5, y: 16, room: 'devops' },
  ...Array.from({ length: 4 }, (_, i) => ({ x: 17 + i % 2 * 3.6, y: i < 2 ? 14.4 : 18.3, room: 'meeting_room' })),
]
export const CATALOG_SEATS = new Map(RAW_EMPLOYEES.map((e, i) => [e[0], seats[i]!]))
export const EXTRA_SEATS: OfficeSeat[] = Array.from({ length: 4 }, (_, i) => ({ x: 24, y: 2.5 + i * 2.8, room: 'dev_floor' }))
export interface OfficePerson extends OfficeSeat { id: string; name: string; role: string; state: string; risk: boolean; live: boolean }
export const STATUS_COLORS: Record<string, string> = { working: '#55d69d', waiting: '#ffc168', blocked: '#ff767d', meeting: '#a9a0f4', walking: '#7ebcff', idle: '#a8b8c6', offline: '#87949d' }
export const STATUS_TEXT: Record<string, string> = { working: 'Working', waiting: 'Waiting approval', blocked: 'Blocked', meeting: 'In meeting', walking: 'Walking', idle: 'Idle', offline: 'Layout preview' }

/** Keep slots after removals so reconnects and additions never move other people. */
export function assignOfficeSeats(ids: string[], assigned: Map<string, OfficeSeat>): Map<string, OfficeSeat> {
  for (const id of [...ids].sort()) {
    if (assigned.has(id)) continue
    const known = CATALOG_SEATS.get(id)
    if (known) { assigned.set(id, known); continue }
    const occupied = new Set([...assigned.values()].map((s) => `${s.x},${s.y}`))
    const seat = EXTRA_SEATS.find((s) => !occupied.has(`${s.x},${s.y}`))
    if (seat) assigned.set(id, seat)
  }
  return assigned
}

function raised(c: CanvasRenderingContext2D, z: number, draw: () => void) { c.save(); c.translate(0, -z); draw(); c.restore() }
function plant(c: CanvasRenderingContext2D, x: number, y: number) {
  const p = iso(x, y)
  c.fillStyle = '#25342c33'; c.beginPath(); c.ellipse(p.x, p.y, 19, 8, 0, 0, 7); c.fill()
  box(c, x - .2, y - .2, .4, .4, 17, '#d3956d', '#a7664d', '#bf7d59')
  c.strokeStyle = '#5c6445'; c.lineWidth = 3; c.beginPath(); c.moveTo(p.x, p.y - 16); c.lineTo(p.x, p.y - 47); c.stroke()
  for (let i = 0; i < 9; i++) {
    const a = i * 2.4, dx = Math.cos(a) * 12, dy = Math.sin(a) * 14
    c.fillStyle = ['#507f52', '#6c9d61', '#82ab6c'][i % 3]!
    c.beginPath(); c.ellipse(p.x + dx, p.y - 39 + dy, 12, 5, a, 0, Math.PI * 2); c.fill()
    c.strokeStyle = '#416946'; c.lineWidth = .7; c.stroke()
  }
}
function cabinet(c: CanvasRenderingContext2D, x: number, y: number, server = false) {
  box(c, x, y, 1.5, .6, 57, '#a78f74', '#64574e', '#4b4641')
  const p = iso(x, y + .62)
  c.save(); c.transform(1, .5, 0, 1, p.x, p.y)
  c.fillStyle = server ? '#27343f' : '#55453a'; c.fillRect(2, -53, 43, 49)
  for (let row = 0; row < 4; row++) {
    if (server) {
      c.fillStyle = '#56616a'; c.fillRect(5, -50 + row * 12, 36, 9)
      c.fillStyle = '#69d6b2'; c.fillRect(8, -47 + row * 12, 3, 2)
      c.fillStyle = '#263743'; for (let i = 0; i < 5; i++) c.fillRect(18 + i * 4, -48 + row * 12, 2, 5)
    } else {
      for (let i = 0; i < 8; i++) { c.fillStyle = ['#728b7e', '#b6a780', '#8c6259', '#768999'][i % 4]!; c.fillRect(5 + i * 4.5, -50 + row * 12, 3, 9 - i % 3) }
      c.fillStyle = '#b39473'; c.fillRect(3, -40 + row * 12, 40, 2)
    }
  }
  c.restore()
}
function cooler(c: CanvasRenderingContext2D, x: number, y: number) {
  box(c, x, y, .65, .65, 32, '#dbe3de', '#a5b9bd', '#819ca4')
  raised(c, 32, () => box(c, x + .12, y + .12, .42, .42, 24, '#a5e2eb', '#65b6d1', '#7ac8dd'))
  const p = iso(x, y + .7); c.fillStyle = '#3e6577'; c.fillRect(p.x + 4, p.y - 23, 9, 12)
  c.fillStyle = '#c1f4f4'; c.fillRect(p.x + 6, p.y - 21, 3, 3)
}
function monitor(c: CanvasRenderingContext2D, x: number, y: number) {
  raised(c, 28, () => {
    box(c, x + .25, y, .45, .35, 2, '#62727a', '#34454e', '#43525b')
    box(c, x + .43, y + .1, .08, .08, 9, '#7d8f92', '#4c5d65', '#3c4f58')
  })
  const p = iso(x, y + .1)
  c.save(); c.transform(1, .5, 0, 1, p.x, p.y - 36)
  c.fillStyle = '#35444e'; c.fillRect(-2, -24, 36, 25)
  c.fillStyle = '#172c35'; c.fillRect(1, -21, 30, 19)
  for (let i = 0; i < 5; i++) { c.fillStyle = i % 2 ? '#85bfbb' : '#a6cb8e'; c.fillRect(4, -18 + i * 3, 8 + (i * 7) % 18, 1) }
  c.fillStyle = '#8ca1a4'; c.fillRect(13, 0, 7, 2); c.restore()
}
function desk(c: CanvasRenderingContext2D, x: number, y: number, w = 2.6, computer = true, d = 1.25) {
  box(c, x + .12, y + .15, w + .12, d + .18, 0, '#55433429', '', '')
  for (const dx of [.12, w - .24]) box(c, x + dx, y + .8, .13, .16, 27, '#847364', '#65554a', '#493e39')
  box(c, x + w - .6, y + .15, .5, .85, 25, '#b28e68', '#987051', '#77563f')
  raised(c, 26, () => box(c, x, y, w, d, 4, '#cea477', '#936b50', '#ae805a'))
  for (let i = 1; i < 6; i++) {
    const a = iso(x + .12, y + i * d / 6), b = iso(x + w - .1, y + i * d / 6)
    c.strokeStyle = '#94683e25'; c.lineWidth = .7; c.beginPath(); c.moveTo(a.x, a.y - 30); c.lineTo(b.x, b.y - 30); c.stroke()
  }
  if (computer) {
    monitor(c, x + 1.2, y + .7)
    raised(c, 30, () => box(c, x + .8, y + .1, .7, .27, 1, '#c7c8b9', '#9ba6a5', '#aeb9b8'))
    const p = iso(x + .3, y + .65); c.fillStyle = '#f0ead8'; c.fillRect(p.x - 3, p.y - 36, 7, 8)
    c.strokeStyle = '#d4c4a7'; c.lineWidth = 2; c.strokeRect(p.x + 3, p.y - 35, 3, 5)
  }
}
function person(c: CanvasRenderingContext2D, e: OfficePerson, selected: boolean) {
  const p = iso(e.x, e.y), hash = [...e.id].reduce((n, a) => n + a.charCodeAt(0), 0)
  c.save(); c.translate(p.x, p.y)
  c.fillStyle = '#25303d35'; c.beginPath(); c.ellipse(0, 3, 20, 8, 0, 0, 7); c.fill()
  if (selected || e.state === 'waiting' || e.state === 'blocked') {
    c.strokeStyle = selected ? '#f8e2ad' : STATUS_COLORS[e.state]!; c.lineWidth = 2; c.beginPath(); c.ellipse(0, 2, 23, 10, 0, 0, 7); c.stroke()
  }
  const motion = e as Partial<AnimatedPerson>
  const phase = motion.phase ?? 0
  const stride = motion.walking ? Math.sin(phase * 2) * 5 : 0
  if (motion.facingLeft) c.scale(-1, 1)
  c.translate(0, motion.walking ? -Math.abs(Math.sin(phase * 2)) * 2 : Math.sin(phase * .5) * .6)
  c.fillStyle = '#273749'; c.fillRect(-10, -16, 9, 16 + stride); c.fillRect(3, -16, 9, 16 - stride)
  c.fillStyle = '#26303b'; c.fillRect(-12, -2 + stride, 13, 5); c.fillRect(3, -2 - stride, 13, 5)
  c.fillStyle = SHIRTS[hash % SHIRTS.length]!; c.beginPath(); c.roundRect(-12, -43, 26, 29, [8, 8, 3, 3]); c.fill()
  c.fillStyle = '#ffffff75'; c.fillRect(-7, -39, 3, 19)
  c.fillStyle = '#e9e5d3'; c.fillRect(-2, -39, 6, 4)
  c.fillStyle = '#293944'; c.fillRect(0, -34, 3, 13)
  c.fillStyle = '#ffffff50'; c.fillRect(8, -25, 3, 2)
  const skin = SKINS[hash % SKINS.length]!
  c.fillStyle = skin; c.fillRect(-3, -48, 8, 8)
  c.beginPath(); c.roundRect(-11, -66, 24, 25, 9); c.fill()
  c.fillStyle = HAIRS[hash % HAIRS.length]!; c.beginPath(); c.roundRect(-12, -69, 26, 13, [9, 9, 2, 2]); c.fill()
  c.fillRect(-12, -59, 5, 11)
  c.fillStyle = '#ffffff12'; c.fillRect(-7, -66, 15, 3)
  if (hash % 3 === 0) c.fillRect(9, -60, 6, 24)
  c.fillStyle = '#332c2a'; c.fillRect(-2, -55, 2, 3); c.fillRect(7, -52, 2, 3)
  c.strokeStyle = '#925f4e'; c.lineWidth = 1; c.beginPath(); c.moveTo(3, -46); c.lineTo(8, -46); c.stroke()
  if (hash % 4 === 0) { c.strokeStyle = '#3b414a'; c.lineWidth = 1.5; c.strokeRect(-5, -57, 8, 6); c.strokeRect(5, -54, 8, 6) }
  const hand = e.state === 'working' ? Math.sin(phase * 3) * 2 : stride
  c.strokeStyle = skin; c.lineWidth = 7; c.lineCap = 'round'; c.beginPath(); c.moveTo(-11, -32); c.lineTo(-7, -21); c.lineTo(5, -20 + hand); c.moveTo(13, -31); c.lineTo(motion.wave ? 24 + Math.sin(phase * 3) * 5 : 20, motion.wave ? -59 : -20 - hand); c.stroke()
  if (motion.wave) { c.fillStyle = '#f5e7bf'; c.font = 'bold 11px Arial'; c.fillText('Hey!', 10, -82) }
  c.restore()
}

/** A single coordinate system owns floors, furniture and seated bodies. */
export function paintReferenceOffice(c: CanvasRenderingContext2D, people: OfficePerson[], selectedId?: string | null, time = 0) {
  box(c, 0, 0, 26, 20, -10, '#b8a58d', '#594a42', '#493f39')
  for (const r of OFFICE_ROOMS) {
    for (let x = r.x; x < r.x + r.w; x++) for (let y = r.y; y < r.y + r.h; y++) {
      box(c, x, y, .98, .98, 0, r.colors[(x + y) % 2]!, '', '')
    }
  }
  const items: { d: number; paint: () => void }[] = []
  const add = (x: number, y: number, paint: () => void) => items.push({ d: x + y, paint })
  for (const r of OFFICE_ROOMS) {
    for (let x = r.x; x < r.x + r.w; x++) {
      // Door openings in interior walls connect every room.
      if (r.y > 0 && x === r.x + r.w - 2) continue
      add(x, r.y, () => drawWall(c, x, r.y - 1, 'back'))
    }
    for (let y = r.y; y < r.y + r.h; y++) {
      if (r.x > 0 && y === r.y + r.h - 2) continue
      add(r.x, y, () => drawWall(c, r.x - 1, y, 'left'))
    }
  }
  // Tall windows and notice boards are attached to rear walls, never floating.
  for (const [x, y] of [[1, 0], [5, 0], [10, 0], [16, 0], [21, 0], [1, 9], [16, 12]]) {
    add(x! + 2, y!, () => {
      onWall(c, x!, y! - 1, 'back', 0, 2, 17, 53, '#a5d1d9', '#e2c7a2')
      onWall(c, x!, y! - 1, 'back', .07, .95, 20, 50, '#bce0e1')
      onWall(c, x!, y! - 1, 'back', 1.03, 1.94, 20, 50, '#8dbecf')
    })
  }
  for (const [x, y] of [[.7, 7], [.7, 18], [6.6, 10.2], [8.8, .7], [25, .8], [25, 10.5], [14.8, 18.8], [25, 18.8]]) add(x!, y!, () => plant(c, x!, y!))
  for (const [x, y] of [[.7, 1], [4.4, 9.4], [18, .2], [21, 12.2]]) add(x! + 1.5, y! + .6, () => cabinet(c, x!, y!))
  for (const x of [8.5, 10.3, 12]) add(x + 1.5, 12.8, () => cabinet(c, x, 12.2, true))
  for (const [x, y] of [[23.4, .7], [8.7, 10.5], [24.7, 13.2]]) add(x! + .65, y! + .65, () => cooler(c, x!, y!))
  // Shared coffee point, with cups and a machine on a low timber cabinet.
  add(15, 1.1, () => {
    box(c, 13, .2, 2, .8, 28, '#b99b76', '#8e7056', '#725740')
    raised(c, 28, () => {
      box(c, 13.2, .3, .5, .45, 20, '#52616a', '#35434d', '#28363e')
      box(c, 14.1, .4, .16, .16, 5, '#f4e7cd', '#c9c5b7', '#d8d5c8')
    })
  })
  // Executive rug.
  const rug = [[1.4, 12], [6.8, 12], [6.8, 17.3], [1.4, 17.3]].map(([x,y]) => { const p = iso(x!, y!); return [p.x,p.y] as [number,number] })
  quad(c, rug, '#7d8060'); c.strokeStyle = '#c8bd8b'; c.lineWidth = 3; c.stroke()
  for (const seat of [...seats, ...EXTRA_SEATS]) {
    if (seat.room === 'meeting_room') continue
    const x = seat.x - 1.1, y = seat.y + .55
    add(x + 2.6, y + 1.25, () => desk(c, x, y, seat.room === 'ceo_office' ? 3.4 : 2.6))
    if (seat.room === 'dev_floor') {
      add(x + 2.75, y + 1.35, () => {
        box(c, x + 2.65, y - .45, .09, 1.8, 43, '#e2e4d9', '#a1afad', '#7a8c90')
        raised(c, 29, () => box(c, x + 2.62, y - .35, .12, 1.6, 12, '#e1e6dd', '#bfccc6', '#a9b8b5'))
      })
    }
  }
  // Conference table and wall display.
  add(21.9, 17.2, () => desk(c, 16, 15.4, 6.8, false, 2.2))
  add(18.4, 12.2, () => onWall(c, 15, 11, 'back', 0, 3.2, 18, 53, '#253a48', '#b7aa92'))
  for (const seat of [...seats, ...EXTRA_SEATS]) {
    add(seat.x, seat.y, () => {
      const p = iso(seat.x, seat.y); c.save(); c.translate(p.x, p.y)
  // Chair, seated legs, torso, head and arms are painted as separate layers.
  c.strokeStyle = '#39434d'; c.lineWidth = 3; c.beginPath(); c.moveTo(0, -13); c.lineTo(0, 2); c.moveTo(-13, 5); c.lineTo(13, -1); c.stroke()
  c.fillStyle = '#3d4b5b'; c.beginPath(); c.roundRect(-17, -47, 32, 35, 9); c.fill()
  c.strokeStyle = '#91a0a7'; c.lineWidth = 1.5; c.stroke()
      c.fillStyle = '#607485'; c.fillRect(-16, -22, 31, 8); c.restore()
    })
  }
  // Server LEDs and coffee steam give the room a subtle ambient rhythm.
  add(15, 1.2, () => {
    const p = iso(13.3, .5); c.strokeStyle = '#eee4d088'; c.lineWidth = 1.3
    for (let i = 0; i < 3; i++) { c.beginPath(); c.moveTo(p.x + i * 4, p.y - 51); c.quadraticCurveTo(p.x + i * 4 + Math.sin(time * 2 + i) * 4, p.y - 58, p.x + i * 4, p.y - 66); c.stroke() }
  })
  people.forEach((e) => add(e.x + .1, e.y + .1, () => person(c, e, e.id === selectedId)))
  items.sort((a, b) => a.d - b.d).forEach((i) => i.paint())
  for (const r of OFFICE_ROOMS) {
    const p = iso(r.x + r.w / 2, r.y + r.h - .6)
    c.font = 'bold 17px "Arial", sans-serif'; c.textAlign = 'center'; c.lineWidth = 4
    c.strokeStyle = '#3c3936'; c.strokeText(r.name, p.x, p.y)
    c.fillStyle = '#f5ecda'; c.fillText(r.name, p.x, p.y)
  }
}
