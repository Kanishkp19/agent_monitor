/**
 * Office engine harness (dev only — `office-harness.html`).
 *
 * Runs the EXACT production engine modules (WorldNav, MotionSystem,
 * BehaviorSystem, PersonRenderer, Furniture) on a bare canvas, bypassing
 * the app shell (which gates at 1024px and needs the API up). Used to
 * calibrate furniture rects, watch behaviors, and verify the atlas in
 * isolation. Not part of the app bundle: vite only bundles what the
 * entry HTML imports.
 *
 * Controls: drag = pan, wheel = zoom, N or button = navdebug,
 * speed buttons drive the same dt pipeline as the app's speed control.
 */

import { iso, depth } from '../engine/IsoMath'
import { loadRoomBackgrounds, drawRoomLabels, type WorldData, type RoomBackground } from '../engine/WorldRenderer'
import { drawPerson, drawHalo, loadAtlas, setAtlas } from '../engine/PersonRenderer'
import { createDefaultEmployees } from '../engine/EmployeeCatalog'
import { updateMotion } from '../engine/MotionSystem'
import { updateBehavior, tickBubbles } from '../engine/BehaviorSystem'
import { buildWorldNav, drawNavDebug, type WorldNav } from '../engine/WorldNav'
import type { SimEmployee, SimFsmState } from '../systems/Types'

const HALO: Partial<Record<SimFsmState, string>> = {
  working: '#3FCF8E',
  waiting: '#F2A73B',
  blocked: '#E5484D',
  meeting: '#3D7BFF',
}

const canvas = document.getElementById('stage') as HTMLCanvasElement
const ctx = canvas.getContext('2d')!

const employees: SimEmployee[] = createDefaultEmployees()
const nav: WorldNav = buildWorldNav()

let backgrounds: RoomBackground[] = []
let world: WorldData | null = null

// ── Controls ──────────────────────────────────────────────────────────
let speed = 1
let navDebug = false

const btnPause = document.getElementById('btn-pause') as HTMLButtonElement
const btn1x = document.getElementById('btn-1x') as HTMLButtonElement
const btn3x = document.getElementById('btn-3x') as HTMLButtonElement
const btnNav = document.getElementById('btn-nav') as HTMLButtonElement

function setSpeedButtons(): void {
  btnPause.classList.toggle('active', speed === 0)
  btn1x.classList.toggle('active', speed === 1)
  btn3x.classList.toggle('active', speed === 3)
}

btnPause.addEventListener('click', () => { speed = 0; setSpeedButtons() })
btn1x.addEventListener('click', () => { speed = 1; setSpeedButtons() })
btn3x.addEventListener('click', () => { speed = 3; setSpeedButtons() })
btnNav.addEventListener('click', () => {
  navDebug = !navDebug
  btnNav.textContent = `navdebug: ${navDebug ? 'on' : 'off'}`
  btnNav.classList.toggle('active', navDebug)
})
window.addEventListener('keydown', (ev) => {
  if (ev.key === 'n' || ev.key === 'N') btnNav.click()
})

// ── Camera ────────────────────────────────────────────────────────────
const cam = { x: 0, y: 0, z: 0.75 }
const size = { vw: 0, vh: 0, dpr: 1 }

function fitCamera(): void {
  if (!world) return
  // Min zoom 0.2: the joined building is wide, small viewports must fit it all.
  cam.z = Math.max(0.2, Math.min((size.vw - 20) / world.WW, (size.vh - 20) / world.WH))
  if (cam.z > 1.4) cam.z = 1.4
  cam.x = world.WW / 2 - world.OX
  cam.y = world.WH / 2 - world.OY
}

function resize(): void {
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  size.vw = window.innerWidth
  size.vh = window.innerHeight
  canvas.width = Math.floor(size.vw * dpr)
  canvas.height = Math.floor(size.vh * dpr)
  canvas.style.width = size.vw + 'px'
  canvas.style.height = size.vh + 'px'
  size.dpr = dpr
}
window.addEventListener('resize', resize)

let dragStart: { x: number; y: number } | null = null
canvas.addEventListener('pointerdown', (ev) => { dragStart = { x: ev.clientX, y: ev.clientY } })
window.addEventListener('pointerup', () => { dragStart = null })
canvas.addEventListener('pointermove', (ev) => {
  if (!dragStart || !(ev.buttons & 1)) { dragStart = null; return }
  cam.x -= (ev.clientX - dragStart.x) / cam.z
  cam.y -= (ev.clientY - dragStart.y) / cam.z
  dragStart = { x: ev.clientX, y: ev.clientY }
})
canvas.addEventListener('wheel', (ev) => {
  ev.preventDefault()
  const ZOOMS = [0.4, 0.6, 0.75, 1, 1.4, 2]
  let closest = 0
  let best = 1e9
  ZOOMS.forEach((z, k) => {
    const d = Math.abs(z - cam.z)
    if (d < best) { best = d; closest = k }
  })
  const dir = ev.deltaY < 0 ? 1 : -1
  cam.z = ZOOMS[Math.max(0, Math.min(ZOOMS.length - 1, closest + dir))]!
}, { passive: false })

// ── Boot ──────────────────────────────────────────────────────────────
resize()

loadRoomBackgrounds().then(({ backgrounds: bgs, bounds }) => {
  backgrounds = bgs
  world = bounds
  fitCamera()
}).catch((err) => console.error('backgrounds:', err))

loadAtlas().then((sheet) => {
  setAtlas(sheet)
  if (!sheet) console.warn('atlas unavailable — legacy/procedural fallbacks will render')
})

// ── Loop ──────────────────────────────────────────────────────────────
let last = 0

function render(now: number): void {
  requestAnimationFrame(render)

  const wallDt = Math.min(0.1, (now - last) / 1000 || 0)
  last = now
  const dt = speed === 0 ? 0 : wallDt * speed

  updateBehavior(employees, nav.grid, dt, speed)
  tickBubbles(employees, dt)
  updateMotion(employees, nav.grid, dt)

  const beatWave = (Math.sin(now / 700) + 1) / 2

  ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0)
  ctx.fillStyle = '#080D16'
  ctx.fillRect(0, 0, size.vw, size.vh)

  ctx.save()
  ctx.translate(size.vw / 2, size.vh / 2)
  ctx.scale(cam.z, cam.z)
  ctx.translate(-cam.x, -cam.y)
  ctx.imageSmoothingEnabled = false

  for (const bg of backgrounds) ctx.drawImage(bg.img, bg.wx, bg.wy)
  drawRoomLabels(ctx)
  if (navDebug) drawNavDebug(ctx, nav)

  const sorted = [...employees].sort(
    (a, b) => depth(a.pos.x, a.pos.y, 2) - depth(b.pos.x, b.pos.y, 2),
  )
  for (const e of sorted) {
    const p = iso(e.pos.x, e.pos.y)
    const halo = HALO[e.fsm]
    if (halo) {
      drawHalo(ctx, p.x, p.y + 6, halo, e.fsm === 'waiting' ? 0.45 + beatWave * 0.5 : 0.8, 17, 8.5)
    }
    drawPerson(ctx, p.x, p.y, e)
  }

  ctx.restore()
}
requestAnimationFrame(render)
