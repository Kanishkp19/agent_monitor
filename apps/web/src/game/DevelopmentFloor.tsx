import { useEffect, useRef, useState } from 'react'
import { useSim } from '@/stores/simStore'
import { DEVELOPMENT, developmentTour, projectedFoot, sampleTour } from './engine/DevelopmentScene'
import { paintDevelopment, paintFloor, STATE_COLORS, type FloorPerson } from './engine/DevelopmentRenderer'

interface Props { onSelect: (id: string | null) => void; selectedId?: string | null }
const tour = developmentTour(DEVELOPMENT.desks[0]!.seat)
const WIDTH = 840, HEIGHT = 490, ORIGIN_X = 365, ORIGIN_Y = 93

/** Preview boundary: only reads telemetry; motion never changes task state. */
export function DevelopmentFloor({ onSelect, selectedId }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const host = useRef<HTMLDivElement>(null)
  const avatars = useSim((s) => s.avatars)
  const speed = useSim((s) => s.speed)
  const error = useSim((s) => s.error)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [demo, setDemo] = useState(false)
  const [motion, setMotion] = useState(false)
  const [size, setSize] = useState({ w: 1, h: 1 })
  const [reduced, setReduced] = useState(false)
  const time = useRef(0)
  const hit = useRef<{ id: string; x: number; y: number }[]>([])
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const [demoSelection, setDemoSelection] = useState<string | null>(null)
  const live = Object.values(avatars).sort((a, b) => a.employee_id.localeCompare(b.employee_id)).slice(0, 4)
  const people = demo
    ? ['working', 'waiting', 'blocked', 'idle'].map((state, i) => ({ id: `fixture-${i}`, name: ['Alex Chen', 'Sam Rivera', 'Jordan Lee', 'Morgan Park'][i]!, state }))
    : live.map((a) => ({ id: a.employee_id, name: a.name, state: a.fsm }))
  const currentSelection = demo ? demoSelection : selectedId
  const scale = Math.max(.1, Math.min(size.w / WIDTH, (size.h - 150) / HEIGHT)) * zoom
  const offset = { x: size.w / 2 + pan.x, y: (size.h + 60) / 2 + pan.y }
  const snapshot = useRef({ people, speed, scale, offset, currentSelection, reduced, motion })
  snapshot.current = { people, speed, scale, offset, currentSelection, reduced, motion }

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update(); media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    const el = host.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const cv = canvas.current
    const c = cv?.getContext('2d')
    if (!cv || !c) return
    const background = document.createElement('canvas')
    background.width = WIDTH; background.height = HEIGHT
    const bg = background.getContext('2d')!
    bg.translate(ORIGIN_X, ORIGIN_Y); paintFloor(bg)
    let raf = 0, last = 0
    const render = (now: number) => {
      const s = snapshot.current
      if (last && !s.reduced && s.motion) time.current += Math.min((now - last) / 1000, .05) * Math.min(s.speed, 3)
      last = now
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      const bounds = cv.getBoundingClientRect()
      const w = Math.round(bounds.width * dpr), h = Math.round(bounds.height * dpr)
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h }
      c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, bounds.width, bounds.height)
      c.save(); c.translate(s.offset.x, s.offset.y); c.scale(s.scale, s.scale)
      c.translate(-WIDTH / 2, -HEIGHT / 2)
      c.drawImage(background, 0, 0)
      c.translate(ORIGIN_X, ORIGIN_Y)
      const rendered: FloorPerson[] = s.people.map((p, i) => {
        const pose = i === 0 && s.motion && !s.reduced ? sampleTour(tour, time.current) : { position: DEVELOPMENT.desks[i]!.seat, seated: true, phase: 0 }
        return { ...p, ...pose }
      })
      paintDevelopment(c, rendered, s.currentSelection)
      c.restore()
      hit.current = rendered.map((p) => {
        const foot = projectedFoot(p.position, p.seated)
        return { id: p.id, x: s.offset.x + (foot.x + ORIGIN_X - WIDTH / 2) * s.scale, y: s.offset.y + (foot.y + ORIGIN_Y - HEIGHT / 2 - 30) * s.scale }
      })
      // Screen-space badges keep a constant readable type size. Fixed columns
      // avoid overlaps; connectors attach each badge to its actual employee.
      rendered.forEach((p, i) => {
        const foot = hit.current[i]!
        const cell = bounds.width / Math.max(1, rendered.length)
        const x = cell * (i + .5), y = 114
        c.strokeStyle = p.id === s.currentSelection ? '#c4e7f8' : '#7b8b9b70'
        c.lineWidth = 1; c.beginPath(); c.moveTo(x, y + 12); c.lineTo(foot.x, foot.y - 20 * s.scale); c.stroke()
        c.fillStyle = '#111e2c'; c.beginPath(); c.roundRect(x - cell / 2 + 4, y - 36, cell - 8, 48, 7); c.fill()
        c.textAlign = 'center'; c.font = '600 12px system-ui'; c.fillStyle = '#edf4fa'
        c.fillText(p.name, x, y - 17, cell - 18)
        c.font = '11px system-ui'; c.fillStyle = STATE_COLORS[p.state] ?? '#bbc8d3'
        c.fillText(`${p.state === 'blocked' ? '×' : p.state === 'waiting' ? '◷' : '●'} ${p.state}`, x, y, cell - 18)
      })
      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [])

  function select(id: string | null) { if (demo) setDemoSelection(id); else onSelect(id) }
  function fit() { setZoom(1); setPan({ x: 0, y: 0 }) }
  const button = 'rounded border border-line bg-ink-800 px-3 py-1.5 text-xs text-text hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-blue-300'

  return <div ref={host} className="relative h-full min-h-96 w-full overflow-hidden" style={{ background: 'radial-gradient(ellipse at 50% 60%, #293c49, #101b29 75%)' }}>
    <div className="absolute inset-x-0 top-0 z-10 flex flex-wrap items-start justify-between gap-2 p-4">
      <div><p className="text-[10px] uppercase tracking-[.2em] text-text-dim">Office / Development</p><h2 className="text-lg font-semibold text-text">A place for good work.</h2>
        <p className="text-xs text-text-dim">{demo ? 'Demo fixtures · isolated from live telemetry' : `Live preview · ${live.length} of ${Object.keys(avatars).length} employees`} · two desk clusters</p></div>
      <button className={button} onClick={() => { setDemo(!demo); time.current = 0 }}>{demo ? 'Use live state' : 'Try demo fixtures'}</button>
    </div>
    <canvas ref={canvas} className="h-full w-full touch-none" aria-label="Development floor with layered desks and employees" tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Escape') { select(null); fit() } }}
      onPointerDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, moved: false }; e.currentTarget.setPointerCapture(e.pointerId) }}
      onPointerMove={(e) => {
        const d = drag.current; if (!d) return
        const dx = e.clientX - d.x, dy = e.clientY - d.y
        if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
        if (d.moved) setPan((p) => ({ x: Math.max(-size.w / 2, Math.min(size.w / 2, p.x + dx)), y: Math.max(-size.h / 3, Math.min(size.h / 3, p.y + dy)) }))
        d.x = e.clientX; d.y = e.clientY
      }}
      onPointerCancel={() => { drag.current = null }}
      onPointerUp={(e) => {
        const d = drag.current; drag.current = null
        if (!d || d.moved) return
        const rect = e.currentTarget.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top
        const cell = size.w / Math.max(1, people.length)
        const badge = y >= 78 && y <= 126 ? people[Math.floor(x / cell)] : null
        select(badge?.id ?? [...hit.current].reverse().find((p) => Math.hypot(p.x - x, p.y - y) < 28 * Math.max(.8, scale))?.id ?? null)
      }} />
    {!people.length && <div className="absolute inset-x-4 top-36 rounded border border-line bg-ink-900/95 p-3 text-sm text-text" role="status">
      {error ? 'Telemetry unavailable. Return to the live view to reconnect, or try the demo fixtures.' : 'Waiting for employee telemetry. Try demo fixtures to explore the development floor.'}
    </div>}
    <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-2 p-4">
      <div className="flex flex-wrap gap-1">
        <button className={button} aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(.6, z - .2))}>−</button>
        <button className={button} onClick={fit}>Fit floor</button>
        <button className={button} aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(2, z + .2))}>+</button>
        <button className={button} aria-pressed={motion} disabled={reduced} onClick={() => { setMotion(!motion); time.current = 0 }}>{motion ? 'Seat employee' : 'Preview walk'}</button>
      </div>
      <div className="flex flex-wrap gap-1" aria-label="Select employee">
        {people.map((p) => <button key={p.id} className={button} aria-pressed={p.id === currentSelection} onClick={() => select(p.id)}>{p.name.split(' ')[0]} · {p.state}</button>)}
      </div>
      {demo && demoSelection && <p role="status" className="w-full text-right text-xs text-text-dim">Demo selection · {people.find((p) => p.id === demoSelection)?.name} · {people.find((p) => p.id === demoSelection)?.state}</p>}
    </div>
  </div>
}
