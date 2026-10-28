import { useEffect, useMemo, useRef, useState } from 'react'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'
import { RAW_EMPLOYEES } from './engine/EmployeeCatalog'
import { animateOfficePerson } from './engine/OfficeLife'
import { iso } from './engine/IsoMath'
import { assignOfficeSeats, OFFICE_ROOMS, paintReferenceOffice, STATUS_COLORS, STATUS_TEXT, type OfficePerson, type OfficeSeat } from './engine/ReferenceScene'

interface Props { onSelect: (id: string | null) => void; selectedId?: string | null }
const control = 'rounded-md border border-white/15 bg-[#17212c] px-3 py-2 text-xs text-[#dbe4e9] hover:bg-[#273745] focus-visible:outline-2 focus-visible:outline-[#e6bd7d]'

export function ReferenceOffice({ onSelect, selectedId }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null), host = useRef<HTMLDivElement>(null)
  const assigned = useRef(new Map<string, OfficeSeat>())
  const connected = useTelemetry((s) => s.connected)
  const avatars = useSim((s) => s.avatars), error = useSim((s) => s.error)
  const speed = useSim((s) => s.speed)
  const [life, setLife] = useState(true), [time, setTime] = useState(0), [waveUntil, setWaveUntil] = useState(0)
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update(); media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (!life || reduced || speed === 0) return
    let frame = 0, last = 0
    const tick = (now: number) => {
      if (!last) last = now
      if (now - last >= 33) {
        const dt = Math.min((now - last) / 1000, .1); last = now
        if (!document.hidden) setTime((t) => t + dt * Math.min(speed, 2))
      }
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [life, reduced, speed])
  const [size, setSize] = useState({ w: 1, h: 1 })
  const [zoom, setZoom] = useState(1), [pan, setPan] = useState({ x: 0, y: 0 })
  const [room, setRoom] = useState('all'), [labels, setLabels] = useState(true)
  const [hovered, setHovered] = useState<string | null>(null)
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const live = Object.values(avatars), preview = live.length === 0
  const seatedPeople = useMemo(() => {
    const source = Object.values(avatars)
    assignOfficeSeats(source.map((a) => a.employee_id), assigned.current)
    if (!source.length) return RAW_EMPLOYEES.map(([id, name, role]) => {
      assignOfficeSeats([id], assigned.current)
      return { ...assigned.current.get(id)!, id, name, role, state: 'offline', risk: false, live: false }
    })
    return source.flatMap((a): OfficePerson[] => {
      const seat = assigned.current.get(a.employee_id)
      return seat ? [{ ...seat, id: a.employee_id, name: a.name, role: a.role, state: a.fsm, risk: a.badge === 'anomaly' || a.risk_score >= 70, live: true }] : []
    })
  }, [avatars])
  const people = seatedPeople.map((p) => animateOfficePerson(p, time, !reduced, waveUntil))
  const focused = OFFICE_ROOMS.find((r) => r.id === room)
  const center = focused ? iso(focused.x + focused.w / 2, focused.y + focused.h / 2) : { x: 96, y: 330 }
  const bounds = focused ? { w: (focused.w + focused.h) * 32 + 100, h: (focused.w + focused.h) * 16 + 130 } : { w: 1540, h: 850 }
  const scale = Math.max(.05, Math.min((size.w - 32) / bounds.w, (size.h - 150) / bounds.h)) * zoom
  const origin = { x: size.w / 2 - center.x * scale + pan.x, y: (size.h + 32) / 2 - center.y * scale + pan.y }
  const screen = (p: OfficePerson) => { const foot = iso(p.x, p.y); return { x: origin.x + foot.x * scale, y: origin.y + foot.y * scale } }
  const fit = () => { setZoom(1); setPan({ x: 0, y: 0 }) }
  useEffect(() => {
    if (!host.current) return
    const resize = new ResizeObserver(([entry]) => { if (entry) setSize({ w: entry.contentRect.width, h: entry.contentRect.height }) })
    resize.observe(host.current)
    return () => resize.disconnect()
  }, [])
  useEffect(() => {
    const cv = canvas.current, c = cv?.getContext('2d')
    if (!cv || !c) return
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    if (cv.width !== Math.round(size.w * dpr)) cv.width = Math.round(size.w * dpr)
    if (cv.height !== Math.round(size.h * dpr)) cv.height = Math.round(size.h * dpr)
    c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, size.w, size.h)
    c.translate(origin.x, origin.y); c.scale(scale, scale)
    paintReferenceOffice(c, people, selectedId ?? hovered, time)
  }, [size, scale, origin.x, origin.y, people, selectedId, hovered, time])
  const occupied: { x: number; y: number; w: number; h: number }[] = []
  const plates = [...people].sort((a, b) => {
    const priority = (p: OfficePerson) => p.id === selectedId || p.id === hovered ? 10 : p.state === 'blocked' ? 7 : p.state === 'waiting' || p.risk ? 5 : p.room !== 'dev_floor' ? 2 : 0
    return priority(b) - priority(a) || a.id.localeCompare(b.id)
  }).flatMap((p) => {
    if (focused && p.room !== room) return []
    const important = p.id === selectedId || p.id === hovered || p.state === 'blocked' || p.state === 'waiting' || p.risk
    if (!labels && !important) return []
    const pos = screen(p), w = important ? 160 : 106, h = important ? 43 : 25
    const x = Math.max(8, Math.min(size.w - w - 8, pos.x - w / 2)), baseY = pos.y - 78 * scale - h
    const y = (important ? [baseY, baseY - h - 8, baseY + h + 8, baseY - 2 * h - 16] : [baseY]).find((y) =>
      y >= 112 && y + h <= size.h - 65 && !occupied.some((r) => x < r.x + r.w + 5 && x + w + 5 > r.x && y < r.y + r.h + 4 && y + h + 4 > r.y))
    if (y === undefined || pos.x < 0 || pos.x > size.w) return []
    occupied.push({ x, y, w, h }); return [{ p, x, y, w, h, important, anchor: { x: pos.x, y: pos.y - 70 * scale } }]
  })
  const selected = people.find((p) => p.id === (hovered ?? selectedId))
  const hitPerson = (x: number, y: number) => [...people].reverse().find((p) => { const s = screen(p); return Math.abs(s.x - x) < 24 * scale && y > s.y - 70 * scale && y < s.y + 6 })
  return <section data-life-time={time.toFixed(2)} ref={host} className="relative h-full min-h-[420px] overflow-hidden bg-[#10171e]" aria-label="Interactive live office simulation" style={{ backgroundImage: 'radial-gradient(ellipse at 50% 48%, #263039 0%, #151e27 55%, #10171e 85%)' }}>
    <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-5">
      <div><p className="text-[10px] font-semibold tracking-[.24em] text-[#b5a58d]">AGENTSHIELD / WORKSPACE</p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight text-[#f0e9dc]">A day at the office</h1>
        <p className="mt-1 text-[11px] text-[#a4b0bb]" role="status">{preview ? 'Layout preview · waiting for live employee telemetry' : `${live.length} employees · ${error || !connected ? 'Disconnected · last known state' : 'Office life · live status'}`}</p>
      </div>
      <div className="pointer-events-auto flex gap-2">
        <label className="sr-only" htmlFor="office-room">Focus room</label>
        <select id="office-room" className={control} value={room} onChange={(e) => { setRoom(e.target.value); fit() }}>
          <option value="all">Entire office</option>{OFFICE_ROOMS.map((r) => <option key={r.id} value={r.id}>{r.name.toLowerCase().replace(/\b\w/g, (s) => s.toUpperCase())}</option>)}
        </select><button className={control} aria-pressed={labels} onClick={() => setLabels(!labels)}>Names</button>
      </div>
    </header>
    <canvas ref={canvas} tabIndex={0}
      title="Drag or use arrow keys to pan. Double-click a room to focus. Press 0 to fit."
      onDoubleClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect()
        const x = (e.clientX - rect.left - origin.x) / scale, y = (e.clientY - rect.top - origin.y) / scale
        const tx = x / 64 + y / 32, ty = y / 32 - x / 64
        const target = OFFICE_ROOMS.find((r) => tx >= r.x && tx < r.x + r.w && ty >= r.y && ty < r.y + r.h)
        if (target) { setRoom(target.id); fit() }
      }}
      onKeyDown={(e) => {
        const move: Record<string, [number, number]> = { ArrowLeft: [40, 0], ArrowRight: [-40, 0], ArrowUp: [0, 40], ArrowDown: [0, -40] }
        const delta = move[e.key]
        if (delta) { e.preventDefault(); setPan((p) => ({ x: Math.max(-size.w, Math.min(size.w, p.x + delta[0])), y: Math.max(-size.h, Math.min(size.h, p.y + delta[1])) })) }
        if (e.key === '0') fit()
      }} className="h-full w-full touch-none" aria-label="Office floor plan. Use the employee selector to open employee details."
      onWheel={(e) => setZoom((z) => Math.max(.7, Math.min(2.8, z * (e.deltaY < 0 ? 1.1 : .9))))}
      onPointerDown={(e) => { if (e.button !== 0) return; drag.current = { x: e.clientX, y: e.clientY, moved: false }; e.currentTarget.setPointerCapture(e.pointerId) }}
      onPointerMove={(e) => {
        const d = drag.current
        if (d) {
          const dx = e.clientX - d.x, dy = e.clientY - d.y
          if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
          if (d.moved) { setPan((p) => ({ x: Math.max(-size.w, Math.min(size.w, p.x + dx)), y: Math.max(-size.h, Math.min(size.h, p.y + dy)) })); d.x = e.clientX; d.y = e.clientY }
          return
        }
        const r = e.currentTarget.getBoundingClientRect(), hit = hitPerson(e.clientX - r.left, e.clientY - r.top)
        setHovered(hit?.id ?? null); e.currentTarget.style.cursor = hit?.live ? 'pointer' : 'grab'
      }} onPointerLeave={() => setHovered(null)} onPointerCancel={() => { drag.current = null }}
      onPointerUp={(e) => {
        const d = drag.current; drag.current = null
        if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId)
        if (!d || d.moved) return
        const r = e.currentTarget.getBoundingClientRect(), p = hitPerson(e.clientX - r.left, e.clientY - r.top)
        if (p?.live) onSelect(p.id); else if (!p) onSelect(null)
      }} />
    <div className="pointer-events-none absolute inset-0" aria-label="Employee nameplates">
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">{plates.filter((p) => p.important).map((p) => <line key={p.p.id} x1={p.x + p.w / 2} y1={p.y + p.h} x2={p.anchor.x} y2={p.anchor.y} stroke={STATUS_COLORS[p.p.state]} strokeWidth="1" opacity=".6" />)}</svg>
      {plates.map(({ p, x, y, w, h, important }) => <button key={p.id} disabled={!p.live} onClick={() => onSelect(p.id)}
        aria-label={`${p.name}, ${p.role}, ${STATUS_TEXT[p.state] ?? p.state}`} aria-pressed={p.id === selectedId}
        className="pointer-events-auto absolute overflow-hidden rounded border text-left shadow-lg focus-visible:outline-2 focus-visible:outline-[#ffe1a4] disabled:cursor-default"
        style={{ left: x, top: y, width: w, height: h, borderColor: p.id === selectedId ? '#e6bd7d' : '#61707b88', background: '#18212bf5', padding: '3px 7px', color: '#f2eee4' }}>
        <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] font-semibold"><span style={{ background: p.risk ? '#e190d3' : STATUS_COLORS[p.state] }} className="h-2 w-2 shrink-0 rounded-full" />{p.name.split(' ')[0]}{p.role === 'CEO' && ' · CEO'}</span>
        {important && <span className="block truncate text-[10px]" style={{ color: p.risk ? '#e190d3' : STATUS_COLORS[p.state] }}>{p.risk ? 'Risk flagged · ' : ''}{STATUS_TEXT[p.state] ?? p.state}</span>}
      </button>)}
    </div>
    {selected && <div className="pointer-events-none absolute bottom-20 left-5 max-w-[280px] rounded-lg border border-[#64717c] bg-[#18212bf5] px-4 py-3 shadow-xl">
      <p className="text-sm font-semibold text-[#f1e9da]">{selected.name}</p><p className="text-xs text-[#aebcc8]">{selected.role}</p>
      <p className="mt-2 text-xs" style={{ color: STATUS_COLORS[selected.state] }}>{STATUS_TEXT[selected.state]}</p>
      {avatars[selected.id]?.current_task_title && <p className="mt-1 text-xs text-[#d8dedf]">{avatars[selected.id]?.current_task_title}</p>}
    </div>}
    <footer className="absolute inset-x-0 bottom-0 flex flex-wrap items-center justify-between gap-2 border-t border-white/10 bg-[#111a23ed] p-3">
      <div className="flex items-center gap-1"><button className={control} aria-label="Zoom out" onClick={() => setZoom((z) => Math.max(.7, z - .2))}>−</button><button className={control} onClick={fit}>Fit</button><button className={control} aria-label="Zoom in" onClick={() => setZoom((z) => Math.min(2.8, z + .2))}>+</button><button className={control} aria-pressed={life} disabled={reduced} onClick={() => setLife(!life)}>{reduced ? 'Reduced motion' : life ? 'Pause life' : 'Resume life'}</button><button className={control} disabled={reduced || !life || speed === 0} onClick={() => setWaveUntil(time + 3)}>Wave hello</button></div>
      <div className="flex gap-3 text-[10px]" aria-label="Office status counts">{['working', 'waiting', 'blocked'].map((state) => <span key={state} style={{ color: STATUS_COLORS[state] }}>● {STATUS_TEXT[state]} {live.filter((a) => a.fsm === state).length}</span>)}</div>
      <label className="sr-only" htmlFor="office-employee">Select employee</label>
      <select id="office-employee" className={`${control} max-w-[190px]`} value={selectedId ?? ''} disabled={preview} onChange={(e) => onSelect(e.target.value || null)}>
        <option value="">Select employee</option>{live.map((a) => <option key={a.employee_id} value={a.employee_id}>{a.name} · {STATUS_TEXT[a.fsm]}{!people.some((p) => p.id === a.employee_id) ? ' · off floor' : ''}</option>)}
      </select>
    </footer>
  </section>
}
