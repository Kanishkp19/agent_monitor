/**
 * Canvas-based office simulation renderer.
 *
 * Architecture: pre-rendered room art (WorldRenderer) + a data-driven
 * navigation/behavior layer on top:
 * - Furniture: machine-readable footprints + POIs (the twin of the art)
 * - WorldNav:  one global walkability grid carved from room interiors
 * - NavGrid:   A* + collinear smoothing (people route around furniture)
 * - MotionSystem: dt-based path following, distance-synced walk cycle
 * - BehaviorSystem: pacing, breaks, chats, waiting strolls, seated meetings
 * - PersonRenderer: animated atlas characters + halos + speech bubbles
 *
 * The component owns the RAF loop and camera. React owns the surrounding layout.
 * Press `n` on the office route to toggle the nav-debug overlay.
 */

import { useEffect, useRef, useState, useCallback } from 'react'

import { iso, depth } from './engine/IsoMath'
import { loadRoomBackgrounds, drawRoomLabels, type WorldData, type RoomBackground } from './engine/WorldRenderer'
import {
  drawPerson,
  drawHalo,
  getHaloRadii,
  loadCharacterSprites,
  loadAtlas,
  setAtlas,
  type CharacterSpriteMap,
} from './engine/PersonRenderer'
import { createDefaultEmployees } from './engine/EmployeeCatalog'
import { updateMotion } from './engine/MotionSystem'
import { updateBehavior, tickBubbles } from './engine/BehaviorSystem'
import { buildWorldNav, drawNavDebug, type WorldNav } from './engine/WorldNav'
import type { SimEmployee, SimFsmState } from './systems/Types'
import { useSim, type AvatarState } from '@/stores/simStore'

interface OfficeSimulationProps {
  onSelect: (employeeId: string | null) => void
  selectedId?: string | null
}

/** FSM → halo colour mapping. */
const HALO: Partial<Record<SimFsmState, string>> = {
  working: '#3FCF8E',
  waiting: '#F2A73B',
  blocked: '#E5484D',
  meeting: '#3D7BFF',
}

/** Status pill config matching reference screenshot. */
const PILL: Partial<Record<SimFsmState, [string, string]>> = {
  waiting: ['review', '● Waiting Approval'],
  blocked: ['block', '✕ BLOCKED'],
  working: ['allow', '● Working'],
}

/**
 * Snapped zoom ladder (docs/07 §2). Fractional zoom shimmers on pixel art,
 * so every way of zooming — wheel, buttons, fit — lands on one of these.
 */
const ZOOM_LEVELS = [0.2, 0.3, 0.5, 0.75, 1, 1.5, 2]

interface Camera {
  x: number
  y: number
  z: number
}

/** Mounts the interactive office while React retains ownership of surrounding UI. */
export function OfficeSimulation({ onSelect, selectedId }: OfficeSimulationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const hudRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const rafRef = useRef<number>(0)
  const worldRef = useRef<WorldData | null>(null)
  const backgroundsRef = useRef<RoomBackground[]>([])
  const spritesRef = useRef<CharacterSpriteMap>({})
  const employeesRef = useRef<SimEmployee[]>([])
  const navRef = useRef<WorldNav | null>(null)
  const navDebugRef = useRef(false)
  const lastFrameRef = useRef<number>(0)
  const camRef = useRef<Camera>({ x: 0, y: 0, z: 0.55 })
  const [camZ, setCamZ] = useState(0.55)
  const sizeRef = useRef({ vw: 0, vh: 0, dpr: 1 })
  const onSelectRef = useRef(onSelect)
  const selectedIdRef = useRef(selectedId)
  const cardRef = useRef<HTMLDivElement | null>(null)
  const platesRef = useRef<Map<string, {
    plate: HTMLDivElement
    pill: HTMLDivElement
    dot: HTMLSpanElement
  }>>(new Map())

  // Zustand selectors
  const avatars = useSim((s) => s.avatars)
  const speed = useSim((s) => s.speed)
  const avatarsRef = useRef(avatars)
  const speedRef = useRef(speed)

  // Legend counts (screen-space chrome).
  const counts = {
    working: 0,
    waiting: 0,
    blocked: 0,
    flagged: 0,
  }
  for (const a of Object.values(avatars)) {
    if (a.badge === 'anomaly') counts.flagged += 1
    switch (a.fsm) {
      case 'working':
        counts.working += 1
        break
      case 'waiting':
        counts.waiting += 1
        break
      case 'blocked':
        counts.blocked += 1
        break
      default:
        break
    }
  }

  onSelectRef.current = onSelect
  selectedIdRef.current = selectedId
  avatarsRef.current = avatars
  speedRef.current = speed

  // Sync store avatars → internal employees
  useEffect(() => {
    const avs = avatarsRef.current
    for (const e of employeesRef.current) {
      const a = avs[e.id] as AvatarState | undefined
      if (!a) continue
      e.fsm = a.fsm as SimFsmState
      e.risk = a.risk_score
      e.anomaly = a.badge === 'anomaly' || a.risk_score >= 70
      if (a.current_task_title) {
        e.task = { title: a.current_task_title }
      } else {
        e.task = null
      }
      e.showWorking = a.fsm === 'working'
    }
  }, [avatars])

  // Screen projection
  const toScreen = useCallback((wx: number, wy: number) => {
    const { vw, vh } = sizeRef.current
    const cam = camRef.current
    return {
      x: (wx - cam.x) * cam.z + vw / 2,
      y: (wy - cam.y) * cam.z + vh / 2,
    }
  }, [])

  // Fit camera to world
  const fitCamera = useCallback(() => {
    const w = worldRef.current
    if (!w) return
    const { vw, vh } = sizeRef.current
    // Tight pad — a wide dead letterbox reads as a rendering bug, and the
    // building is wide enough that the fit must be allowed to go small.
    const pad = 16
    const z = Math.max(0.2, Math.min((vw - pad) / w.WW, (vh - pad) / w.WH))
    camRef.current.z = z
    setCamZ(z)
    camRef.current.x = w.WW / 2 - w.OX
    camRef.current.y = w.WH / 2 - w.OY
  }, [])

  // One step along the snapped zoom ladder. Zooming keeps the world point
  // under the viewport centre fixed by construction (cam.x/y unchanged).
  const zoomStep = useCallback((dir: 1 | -1) => {
    const cam = camRef.current
    let k = 0
    let best = Infinity
    ZOOM_LEVELS.forEach((z, i) => {
      const d = Math.abs(z - cam.z)
      if (d < best) {
        best = d
        k = i
      }
    })
    const next = ZOOM_LEVELS[Math.max(0, Math.min(ZOOM_LEVELS.length - 1, k + dir))]
    if (next == null || next === cam.z) return
    cam.z = next
    setCamZ(next)
  }, [])

  // Resize handler
  const resize = useCallback(() => {
    const cv = canvasRef.current
    const container = containerRef.current
    if (!cv || !container) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    const vw = container.clientWidth
    const vh = container.clientHeight
    cv.width = Math.floor(vw * dpr)
    cv.height = Math.floor(vh * dpr)
    cv.style.width = vw + 'px'
    cv.style.height = vh + 'px'
    sizeRef.current = { vw, vh, dpr }
  }, [])

  // Build the HUD plates and floating popover card
  const buildHud = useCallback(() => {
    const hud = hudRef.current
    if (!hud) return
    hud.innerHTML = ''
    platesRef.current.clear()

    for (const e of employeesRef.current) {
      // Name plate
      const plate = document.createElement('div')
      plate.className = 'office-plate'

      const dot = document.createElement('span')
      dot.className = 'office-plate-dot'

      const seg1 = document.createElement('div')
      seg1.className = 'office-plate-name'

      if (e.id === 'emp_001') {
        // CEO Vikram
        seg1.innerHTML = '<span style="font-size:10px">👤</span> <span>CEO</span>'
        const seg2 = document.createElement('div')
        seg2.className = 'office-plate-role'
        seg2.textContent = 'Vikram'
        plate.append(seg1, seg2)
      } else if (e.id === 'emp_002' || e.id === 'emp_003') {
        // Sara & Ben
        seg1.innerHTML = `<span style="font-size:10px">👤</span> <span>${e.first}</span>`
        plate.append(seg1)
      } else if (e.id === 'emp_019') {
        // Dev Mark
        seg1.innerHTML = '<span style="font-size:10px">👤</span> <span>Dev</span>'
        const seg2 = document.createElement('div')
        seg2.className = 'office-plate-role'
        seg2.textContent = 'Mark'
        plate.append(seg1, seg2)
      } else {
        // Dev Floor Engineers
        const nameSpan = document.createElement('span')
        nameSpan.textContent = e.first
        seg1.append(dot, nameSpan)

        const seg2 = document.createElement('div')
        seg2.className = 'office-plate-role'
        const roleSpan = document.createElement('span')
        roleSpan.textContent = e.role.replace('Engineering Intern', 'Engineer')
        seg2.append(roleSpan)
        plate.append(seg1, seg2)
      }

      plate.addEventListener('click', (ev) => {
        ev.stopPropagation()
        onSelectRef.current(e.id)
      })
      hud.appendChild(plate)

      // Status pill
      const pill = document.createElement('div')
      pill.className = 'office-pill hidden'
      hud.appendChild(pill)

      platesRef.current.set(e.id, { plate, pill, dot })
    }

    // Floating Popover Inspection Card (matches image.png clickcard)
    const card = document.createElement('div')
    card.className = 'office-card hidden'
    card.innerHTML = `
      <div class="office-card-header">
        <span class="office-card-icon" id="popover-icon">⚠️</span>
        <div>
          <div class="office-card-name" id="popover-name">Rahul</div>
          <div class="office-card-role">
            <span id="popover-role">Engineering Intern</span>
            <span>👤</span>
          </div>
        </div>
      </div>
      <div class="office-card-body">
        <div class="office-card-status" id="popover-status">WAITING FOR APPROVAL</div>
        <div class="office-card-desc" id="popover-desc">Agent attempted production deployment</div>
      </div>
    `
    card.addEventListener('click', (ev) => {
      ev.stopPropagation()
      const targetId = selectedIdRef.current || 'emp_013'
      onSelectRef.current(targetId)
    })
    hud.appendChild(card)
    cardRef.current = card
  }, [])

  // Sync HUD positions
  const syncHud = useCallback(() => {
    const cam = camRef.current
    const show = cam.z >= 0.35
    for (const e of employeesRef.current) {
      const h = platesRef.current.get(e.id)
      if (!h) continue
      const p = iso(e.pos.x, e.pos.y)
      const s = toScreen(p.x, p.y - 52)

      if (show) {
        h.plate.classList.remove('hidden')
        h.plate.classList.toggle('idle', e.fsm === 'idle' || e.fsm === 'meeting')
        h.plate.style.transform = `translate3d(${Math.round(s.x - h.plate.offsetWidth / 2)}px,${Math.round(s.y - 60)}px,0)`
        h.dot.style.background = HALO[e.fsm] || '#64748B'
      } else {
        h.plate.classList.add('hidden')
      }

      const pd = e.anomaly
        ? ['anomaly', `◆ Risk ${e.risk}`]
        : (PILL[e.fsm] as [string, string] | undefined)
      const wantPill = show && pd && (e.fsm !== 'working' || e.showWorking || e.anomaly)

      if (wantPill && pd) {
        h.pill.classList.remove('hidden')
        h.pill.className = 'office-pill ' + pd[0]
        h.pill.textContent = pd[1] ?? ''
        h.pill.style.transform = `translate3d(${Math.round(s.x + 20)}px,${Math.round(s.y - 86)}px,0)`
      } else {
        h.pill.classList.add('hidden')
      }
    }

    // Sync floating popover inspection card
    // Only tracks an explicitly selected employee — never a hardcoded default —
    // so the floor doesn't sprout a card for someone the reader never clicked.
    // Full detail lives in the React employee drawer; this is the pointer.
    const card = cardRef.current
    if (card) {
      const targetEmp = selectedIdRef.current
        ? employeesRef.current.find((e) => e.id === selectedIdRef.current)
        : null

      if (show && targetEmp) {
        const p = iso(targetEmp.pos.x, targetEmp.pos.y)
        const s = toScreen(p.x, p.y - 52)

        const iconEl = card.querySelector('#popover-icon')
        const nameEl = card.querySelector('#popover-name')
        const roleEl = card.querySelector('#popover-role')
        const statusEl = card.querySelector<HTMLElement>('#popover-status')
        const descEl = card.querySelector('#popover-desc')

        if (nameEl) nameEl.textContent = targetEmp.first
        if (roleEl) roleEl.textContent = targetEmp.role

        if (targetEmp.fsm === 'blocked') {
          if (iconEl) iconEl.textContent = '🛑'
          if (statusEl) {
            statusEl.textContent = 'BLOCKED BY POLICY'
            statusEl.style.color = 'var(--color-block)'
          }
          if (descEl) descEl.textContent = targetEmp.task?.title || 'Task blocked by AGENTSHIELD Gate 2'
        } else if (targetEmp.fsm === 'waiting') {
          if (iconEl) iconEl.textContent = '⚠️'
          if (statusEl) {
            statusEl.textContent = 'WAITING FOR APPROVAL'
            statusEl.style.color = 'var(--color-review)'
          }
          if (descEl) descEl.textContent = targetEmp.task?.title || 'Agent attempted production deployment'
        } else if (targetEmp.anomaly) {
          if (iconEl) iconEl.textContent = '⚠️'
          if (statusEl) {
            statusEl.textContent = 'BEHAVIOURAL ANOMALY'
            statusEl.style.color = 'var(--color-anomaly)'
          }
          if (descEl) descEl.textContent = `High risk detected (Score ${targetEmp.risk}/100)`
        } else {
          if (iconEl) iconEl.textContent = 'ℹ️'
          if (statusEl) {
            statusEl.textContent = 'WORKING'
            statusEl.style.color = 'var(--color-allow)'
          }
          if (descEl) descEl.textContent = targetEmp.task?.title || 'Task in progress'
        }

        card.classList.remove('hidden')
        card.style.transform = `translate3d(${Math.round(s.x - 20)}px,${Math.round(s.y + 14)}px,0)`
      } else {
        card.classList.add('hidden')
      }
    }
  }, [toScreen])


  // Main setup
  useEffect(() => {
    const cv = canvasRef.current
    if (!cv) return
    const ctx = cv.getContext('2d')
    if (!ctx) return

    let active = true

    // Initialize employees
    const employees = createDefaultEmployees()
    employeesRef.current = employees

    // Build the nav grid from furniture + room interiors
    navRef.current = buildWorldNav()

    // Load pre-rendered room backgrounds
    loadRoomBackgrounds().then(({ backgrounds, bounds }) => {
      if (!active) return
      backgroundsRef.current = backgrounds
      worldRef.current = bounds
      fitCamera()
    }).catch((err) => {
      console.error('Failed to load room backgrounds:', err)
    })

    // Load the animated atlas (primary) + legacy sprites (fallback)
    loadAtlas().then((sheet) => {
      if (!active) return
      setAtlas(sheet)
      if (!sheet) {
        console.warn('Animated atlas unavailable — falling back to legacy sprites')
      }
    }).catch(() => {
      /* procedural fallback handles it */
    })
    loadCharacterSprites().then((sprites) => {
      if (!active) return
      spritesRef.current = sprites
    }).catch((err) => {
      console.error('Failed to load character sprites:', err)
    })

    // Initial sizing
    resize()
    fitCamera()
    buildHud()

    // Sync initial store state
    const avs = avatarsRef.current
    for (const e of employees) {
      const a = avs[e.id] as AvatarState | undefined
      if (!a) continue
      e.fsm = a.fsm as SimFsmState
      e.risk = a.risk_score
      e.anomaly = a.badge === 'anomaly' || a.risk_score >= 70
    }

    // Camera drag state
    let dragStart: { x: number; y: number } | null = null

    const onPointerDown = (ev: PointerEvent) => {
      dragStart = { x: ev.clientX, y: ev.clientY }
    }
    const onPointerUp = () => {
      dragStart = null
    }
    const onPointerMove = (ev: PointerEvent) => {
      if (!dragStart || !(ev.buttons & 1)) { dragStart = null; return }
      const cam = camRef.current
      cam.x -= (ev.clientX - dragStart.x) / cam.z
      cam.y -= (ev.clientY - dragStart.y) / cam.z
      dragStart = { x: ev.clientX, y: ev.clientY }
    }
    const onWheel = (ev: WheelEvent) => {
      ev.preventDefault()
      const cam = camRef.current
      let closest = 0
      let best = 1e9
      ZOOM_LEVELS.forEach((z, k) => {
        const d = Math.abs(z - cam.z)
        if (d < best) { best = d; closest = k }
      })
      const dir = ev.deltaY < 0 ? 1 : -1
      const next = ZOOM_LEVELS[Math.max(0, Math.min(ZOOM_LEVELS.length - 1, closest + dir))]!
      cam.z = next
      setCamZ(next)
    }
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'n' || ev.key === 'N') {
        navDebugRef.current = !navDebugRef.current
      }
    }

    // Click detection on canvas (for employees)
    const onClick = (ev: MouseEvent) => {
      const cam = camRef.current
      const { vw, vh } = sizeRef.current
      const wx = (ev.offsetX - vw / 2) / cam.z + cam.x
      const wy = (ev.offsetY - vh / 2) / cam.z + cam.y

      let nearest: SimEmployee | null = null
      let nearDist = 30 // click threshold in world pixels
      for (const e of employees) {
        const p = iso(e.pos.x, e.pos.y)
        const dist = Math.sqrt((p.x - wx) ** 2 + (p.y - wy) ** 2)
        if (dist < nearDist) {
          nearDist = dist
          nearest = e
        }
      }
      if (nearest) onSelectRef.current(nearest.id)
    }

    cv.addEventListener('pointerdown', onPointerDown)
    cv.addEventListener('pointerup', onPointerUp)
    cv.addEventListener('pointermove', onPointerMove)
    cv.addEventListener('wheel', onWheel, { passive: false })
    cv.addEventListener('click', onClick)
    window.addEventListener('keydown', onKey)

    // Resize observer
    const ro = new ResizeObserver(() => {
      resize()
    })
    if (containerRef.current) ro.observe(containerRef.current)

    // RAF render loop
    const render = (now: number) => {
      rafRef.current = requestAnimationFrame(render)

      // ── Simulation clock ──────────────────────────────────────────
      // dt is wall seconds clamped (tab-switch guard), scaled by sim speed.
      // speed 0 → dt 0 → people freeze mid-stride.
      const last = lastFrameRef.current || now
      lastFrameRef.current = now
      const wallDt = Math.min(0.1, (now - last) / 1000)
      const spd = speedRef.current
      const dt = spd === 0 ? 0 : wallDt * spd

      updateBehavior(employees, navRef.current?.grid, dt, spd)
      tickBubbles(employees, dt)
      updateMotion(employees, navRef.current?.grid, dt)

      const beatWave = (Math.sin(now / 700) + 1) / 2
      const { vw, vh, dpr } = sizeRef.current
      const cam = camRef.current

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

      // Solid canvas background matching #080D16
      ctx.fillStyle = '#080D16'
      ctx.fillRect(0, 0, vw, vh)

      ctx.save()
      ctx.translate(vw / 2, vh / 2)
      ctx.scale(cam.z, cam.z)
      ctx.translate(-cam.x, -cam.y)
      ctx.imageSmoothingEnabled = false

      // Draw pre-rendered room backgrounds
      for (const bg of backgroundsRef.current) {
        ctx.drawImage(bg.img, bg.wx, bg.wy)
      }

      // Draw room labels
      drawRoomLabels(ctx)

      // Nav debug overlay
      if (navDebugRef.current && navRef.current) {
        drawNavDebug(ctx, navRef.current)
      }

      // Draw employees depth-sorted
      const sortedEmployees = [...employeesRef.current].sort(
        (a, b) => depth(a.pos.x, a.pos.y, 2) - depth(b.pos.x, b.pos.y, 2)
      )

      for (const e of sortedEmployees) {
        const p = iso(e.pos.x, e.pos.y)
        const [hrx, hry] = getHaloRadii(e, spritesRef.current)
        const halo = HALO[e.fsm]
        if (halo) {
          drawHalo(ctx, p.x, p.y + 6, halo, e.fsm === 'waiting' ? 0.45 + beatWave * 0.5 : 0.8, hrx, hry)
        }
        if (e.anomaly) {
          drawHalo(ctx, p.x, p.y + 6, '#E668C3', 0.35 + beatWave * 0.5, hrx, hry)
        }
        drawPerson(ctx, p.x, p.y, e, spritesRef.current)
      }

      ctx.restore()

      // Sync HUD positions
      syncHud()
    }

    rafRef.current = requestAnimationFrame(render)

    return () => {
      active = false
      cancelAnimationFrame(rafRef.current)
      cv.removeEventListener('pointerdown', onPointerDown)
      cv.removeEventListener('pointerup', onPointerUp)
      cv.removeEventListener('pointermove', onPointerMove)
      cv.removeEventListener('wheel', onWheel)
      cv.removeEventListener('click', onClick)
      window.removeEventListener('keydown', onKey)
      ro.disconnect()
    }
  }, [resize, fitCamera, buildHud, syncHud])

  // Re-sync when avatars change
  useEffect(() => {
    const avs = avatars
    for (const e of employeesRef.current) {
      const a = avs[e.id] as AvatarState | undefined
      if (!a) continue
      e.fsm = a.fsm as SimFsmState
      e.risk = a.risk_score
      e.anomaly = a.badge === 'anomaly' || a.risk_score >= 70
      if (a.current_task_title) {
        e.task = { title: a.current_task_title }
      }
    }
  }, [avatars])

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden"
      style={{ background: '#080D16' }}
      aria-label="Interactive live office simulation"
    >
      <canvas
        ref={canvasRef}
        style={{ imageRendering: 'pixelated', cursor: 'grab' }}
      />
      <div
        ref={hudRef}
        className="pointer-events-none absolute inset-0"
        style={{ overflow: 'hidden' }}
      />

      {/* Canvas chrome (docs/07 §1): zoom controls bottom-left, live status
          legend bottom-right. Screen-space, so they stay crisp at every zoom. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between p-3">
        <div className="pointer-events-auto flex items-stretch border border-line bg-ink-900/90 shadow-panel">
          <button
            onClick={() => zoomStep(-1)}
            disabled={camZ <= (ZOOM_LEVELS[0] ?? 0.2)}
            className="flex h-7 w-7 items-center justify-center border-r border-line font-mono text-[13px] leading-none text-text-dim transition-colors hover:bg-ink-700 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Zoom out"
          >
            −
          </button>
          <button
            onClick={fitCamera}
            className="flex h-7 items-center justify-center border-r border-line px-2 font-pixel text-[10px] tracking-[0.04em] text-text-dim transition-colors hover:bg-ink-700 hover:text-text"
            aria-label="Fit office to view"
          >
            FIT
          </button>
          <button
            onClick={() => zoomStep(1)}
            disabled={camZ >= (ZOOM_LEVELS[ZOOM_LEVELS.length - 1] ?? 2)}
            className="flex h-7 w-7 items-center justify-center font-mono text-[13px] leading-none text-text-dim transition-colors hover:bg-ink-700 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
            aria-label="Zoom in"
          >
            +
          </button>
        </div>

        <div className="flex items-center gap-3 border border-line bg-ink-900/90 px-2.5 py-1.5 font-mono text-[10px] tabular-nums shadow-panel">
          <span className="flex items-center gap-1.5 text-allow">
            <span className="h-1.5 w-1.5 rounded-full bg-allow" aria-hidden />
            Working {counts.working}
          </span>
          <span className="flex items-center gap-1.5 text-review">
            <span className="h-1.5 w-1.5 rounded-full bg-review" aria-hidden />
            Waiting {counts.waiting}
          </span>
          <span className="flex items-center gap-1.5 text-block">
            <span className="h-1.5 w-1.5 rounded-full bg-block" aria-hidden />
            Blocked {counts.blocked}
          </span>
          <span className="flex items-center gap-1.5 text-anomaly">
            <span className="h-1.5 w-1.5 rounded-full bg-anomaly" aria-hidden />
            Risk {counts.flagged}
          </span>
        </div>
      </div>
    </div>
  )
}
