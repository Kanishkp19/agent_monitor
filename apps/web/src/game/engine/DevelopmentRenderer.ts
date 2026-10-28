import { box, iso, quad } from './IsoMath'
import { DEVELOPMENT, deskDepth, projectedFoot, sceneDepth, type Point } from './DevelopmentScene'

export interface FloorPerson {
  id: string; name: string; state: string; position: Point; seated: boolean; phase: number
}
export const STATE_COLORS: Record<string, string> = {
  working: '#6de0b1', waiting: '#ffd07d', blocked: '#ff8d91', walking: '#9ebeff', idle: '#b7c2d4', meeting: '#c5a4ff',
}

export function paintFloor(c: CanvasRenderingContext2D) {
  // Cache only architecture. Interactive desks and chairs stay in the depth pass.
  box(c, 0, 0, 14, 11, 9, '#c2c8cd', '#404f61', '#536276')
  for (let y = 0; y < 11; y++) for (let x = 0; x < 14; x++) {
    box(c, x, y, .985, .985, 0, x >= 11 ? '#a7b9ad' : (x + y) % 2 ? '#d9d9d0' : '#e1e0d7', '', '')
  }
  box(c, 0, 0, 11, .12, 72, '#f4eee2', '#c6d0d2', '#abbac0')
  box(c, 0, 0, .12, 11, 72, '#f4eee2', '#bdcbd0', '#9aaeb6')
  // Windows sit on rear walls, with a consistent cool daylight palette.
  for (const x of [1.2, 4.4, 7.6]) {
    box(c, x, .14, 2.1, .05, 60, '#bce0e5', '#8caeb9', '#7897a4')
    box(c, x, .2, 2.1, .08, 24, '#dce5de', '#dce5de', '#dce5de')
  }
  // Interior partition is cut away; doorway has no collision or painted slab.
  for (const [x, y, w, d] of DEVELOPMENT.walls) box(c, x, y, w * .12, d, 12, '#96b5a7', '#648679', '#7f9c91')
  const counter = DEVELOPMENT.counter
  box(c, counter.x, counter.y, counter.w, counter.d, 21, '#d0b192', '#967d69', '#b3977c')
  box(c, 12.45, .65, .55, .5, 40, '#d9e2df', '#69817c', '#90a6a0')
  for (const { x, y } of DEVELOPMENT.plants) {
    box(c, x, y, .55, .55, 14, '#d8b598', '#ac8872', '#bf9980')
    const p = iso(x + .27, y + .27)
    for (const [dx, dy, r] of [[0, -34, 13], [-10, -25, 10], [9, -25, 11]]) {
      c.fillStyle = '#5b947b'; c.beginPath(); c.ellipse(p.x + dx!, p.y + dy!, r!, r! * .8, 0, 0, Math.PI * 2); c.fill()
    }
  }
  const p = iso(12.4, 7)
  c.fillStyle = '#527265'; c.font = 'bold 10px ui-monospace'; c.textAlign = 'center'
  c.fillText('BREAK', p.x, p.y)
}

function person(c: CanvasRenderingContext2D, e: FloorPerson, index: number, selected: boolean) {
  const p = projectedFoot(e.position, e.seated)
  const bob = e.seated ? 0 : Math.sin(e.phase * Math.PI * 2) * 2
  c.fillStyle = '#26364130'; c.beginPath(); c.ellipse(p.x, p.y + 3, 13, 5, 0, 0, Math.PI * 2); c.fill()
  if (selected) {
    c.strokeStyle = '#183e58'; c.lineWidth = 2; c.beginPath(); c.ellipse(p.x, p.y + 3, 17, 7, 0, 0, Math.PI * 2); c.stroke()
  }
  c.save(); c.translate(p.x, p.y - bob + (e.seated ? 6 : 0))
  const leg = e.seated ? 0 : Math.sin(e.phase * Math.PI * 2) * 4
  c.fillStyle = '#33465b'
  if (e.seated) {
    c.fillRect(-17, -17, 24, 6); c.fillRect(-18, -12, 6, 11)
    c.fillStyle = '#253345'; c.fillRect(-22, -2, 10, 4)
  } else {
    c.fillRect(-8, -16, 6, 16 + leg); c.fillRect(2, -16, 6, 16 - leg)
    c.fillStyle = '#253345'; c.fillRect(-10, leg - 2, 9, 4); c.fillRect(2, -leg - 2, 9, 4)
  }
  c.fillStyle = ['#538eac', '#a078a7', '#b48a59', '#598e79'][index % 4]!
  c.beginPath(); c.roundRect(-11, -34, 22, 23, [6, 6, 3, 3]); c.fill()
  const skin = ['#d6a47c', '#ad7758', '#e6bc99', '#bd8b6b'][index % 4]!
  c.fillStyle = skin
  c.fillRect(-13, -27, 5, e.seated ? 10 : 15); c.fillRect(8, -27, 5, e.seated ? 10 : 15)
  if (e.seated) {
    c.lineWidth = 5; c.strokeStyle = skin; c.beginPath()
    c.moveTo(-10, -19); c.lineTo(-24, -11); c.lineTo(-29, -13 + Math.sin(e.phase * 5)); c.stroke()
  }
  c.beginPath(); c.roundRect(-9, -49, 18, 19, 7); c.fill()
  c.fillStyle = '#3a353b'; c.beginPath(); c.roundRect(-10, -51, 20, 10, [7, 7, 2, 2]); c.fill()
  c.fillStyle = '#443c40'; c.fillRect(e.seated ? -5 : 3, -39, 2, 2)
  c.restore()
}

export function paintDevelopment(c: CanvasRenderingContext2D, people: FloorPerson[], selectedId?: string | null) {
  const items: { depth: number; draw: () => void }[] = []
  for (const d of DEVELOPMENT.desks) {
    const seat = iso(d.seat.x, d.seat.y)
    // Seat cushion behind the person; backrest is its own foreground piece.
    items.push({ depth: sceneDepth(d.seat) - .1, draw: () => {
      box(c, d.seat.x - .24, d.seat.y - .24, .48, .48, 10, '#607d89', '#405766', '#4e6877')
    } })
    items.push({ depth: sceneDepth(d.seat) + .1, draw: () => {
      c.fillStyle = '#547582'; c.beginPath(); c.roundRect(seat.x - 11, seat.y - 23, 17, 12, 4); c.fill()
    } })
    items.push({ depth: deskDepth(d), draw: () => {
      for (const x of [d.x + .12, d.x + d.w - .2]) box(c, x, d.y + .6, .12, .12, 23, '#667b84', '#566c75', '#637983')
      c.save(); c.translate(0, -23)
      box(c, d.x, d.y, d.w, d.d, 3, '#dbb997', '#ac8e74', '#c3a083')
      c.restore()
      c.save(); c.translate(0, -26)
      box(c, d.x + .85, d.y + .45, .35, .15, 6, '#6a818b', '#566c76', '#455c67')
      c.translate(0, -6)
      box(c, d.x + .7, d.y + .45, .65, .08, 15, '#394b58', '#455d6a', '#283e4b')
      c.restore()
      const p = iso(d.x + 1, d.y + .46)
      quad(c, [[p.x - 8, p.y - 44], [p.x + 8, p.y - 36], [p.x + 8, p.y - 27], [p.x - 8, p.y - 35]], '#9bc8ce')
      c.save(); c.translate(0, -26)
      box(c, d.x + .5, d.y + .12, .7, .2, 1, '#eee9d9', '#dbd2c0', '#ded8c9')
      c.restore()
    } })
  }
  people.forEach((e, i) => items.push({ depth: sceneDepth(e.position), draw: () => person(c, e, i, e.id === selectedId) }))
  items.sort((a, b) => a.depth - b.depth).forEach((item) => item.draw())
}
