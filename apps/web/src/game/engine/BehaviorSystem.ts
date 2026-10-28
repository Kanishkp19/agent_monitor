/**
 * Behavior system: what bodies do when the governance FSM is idle.
 *
 * `fsm` (what the governance plane says) drives the *state*; this system
 * drives the *body*: blocked people pace anxiously near their desk,
 * waiting people stroll to the window and back, working people take
 * coffee breaks and chat with the neighbor, idle people wander between
 * stroll spots. Meetings seat everyone around the conference table.
 *
 * All randomness is per-decision (not per-frame), so behavior is stable
 * under any frame rate and freezes cleanly at speed 0 (ticks stop).
 *
 * Behavior lifetime uses a tick-accumulated clock (`behaviorUntil` counts
 * down in sim seconds), not wall time — pausing the sim pauses people.
 */

import { walkPath, stopWalking, setFacing } from './MotionSystem'
import { furnitureFor } from './Furniture'
import type { NavGrid } from './NavGrid'
import type { SimEmployee, Activity } from '../systems/Types'

const CHAT_LINES = [
  'pairing on the failing test?',
  'did you see the new policy?',
  'coffee?',
  'PR is up — take a look',
  'the flaky test again…',
  'standup in ten',
  'checking the risk dashboard',
  'who owns this service?',
]

const BREAK_LINES = [
  'refilling coffee',
  'stretching my legs',
  'quick water break',
]

const PACING_LINES = [
  'blocked again…',
  'waiting on approval',
  'why is this gated?',
]

/** Tick all bodies. `dt` is sim seconds (0 when paused). */
export function updateBehavior(
  employees: SimEmployee[],
  nav: NavGrid | undefined,
  dt: number,
  speed: number,
): void {
  if (dt <= 0) return

  for (const e of employees) {
    if (e.behaviorUntil > 0) e.behaviorUntil = Math.max(0, e.behaviorUntil - dt)
    e._nextWander = Math.max(0, e._nextWander - dt)

    if (e.path || e.moving) continue // body busy — behaviors wait for arrival

    switch (e.fsm) {
      case 'blocked':
        behaviorBlocked(e, nav, dt)
        break
      case 'waiting':
        behaviorWaiting(e, nav)
        break
      case 'working':
        behaviorWorking(e, nav)
        break
      case 'meeting':
        behaviorMeeting(e, nav)
        break
      case 'idle':
        behaviorIdle(e, nav)
        break
      case 'walking':
        // Legacy fsm value: treat as idle once the path clears.
        behaviorIdle(e, nav)
        break
    }
  }

  // Chat pairing runs after individual updates.
  updateChats(employees, nav, dt, speed)
}

/* ── Per-state behaviors ─────────────────────────────────────────────── */

function behaviorBlocked(e: SimEmployee, nav: NavGrid | undefined, _dt: number): void {
  // Anxious pacing: short trips around the desk, then back.
  if (e.behavior === 'pace') {
    if (e.behaviorUntil === 0) {
      endBehavior(e, nav, 'stand')
      say(e, PACING_LINES)
    }
    return
  }
  if (e._nextWander > 0) return
  e._nextWander = 2.5 + Math.random() * 4

  const home = e._wanderHome ? { x: e._wanderHome[0], y: e._wanderHome[1] } : homeTile(e)
  e._wanderHome = [home.x, home.y]
  const target = nearTile(nav, home, 1.6)
  if (!target) return
  e.behavior = 'pace'
  e.behaviorUntil = 3 + Math.random() * 4
  walkPath(e, nav, target.x, target.y, () => {
    e.activity = 'stand'
    say(e, PACING_LINES, 0.5)
  })
}

function behaviorWaiting(e: SimEmployee, nav: NavGrid | undefined): void {
  // Thoughtful strolling: window, rack, plant — then back to the desk.
  if (e.behavior === 'stroll') {
    if (e.behaviorUntil === 0) endBehavior(e, nav, homeActivityFor(e))
    return
  }
  if (e._nextWander > 0) return
  e._nextWander = 4 + Math.random() * 6

  const f = furnitureFor(e.room)
  const spot = pick(f.breaks.length > 0 ? f.breaks : f.strolls)
  if (!spot) return
  e.behavior = 'stroll'
  e.behaviorUntil = 6 + Math.random() * 6
  walkPath(e, nav, spot[0], spot[1], () => {
    e.activity = 'stand'
    say(e, ['waiting for the approval…'], 0.4)
    // linger, then the until-timer returns us home
  })
}

function behaviorWorking(e: SimEmployee, nav: NavGrid | undefined): void {
  // Coffee breaks + bathroom-style wanders, but the desk is home base.
  if (e.behavior === 'break') {
    if (e.behaviorUntil === 0) endBehavior(e, nav, 'desk')
    return
  }
  if (e.behavior === 'chat') {
    if (e.behaviorUntil === 0) endBehavior(e, nav, 'desk')
    return
  }
  if (e._nextWander > 0) return
  e._nextWander = 14 + Math.random() * 22 // productive people mostly sit

  if (Math.random() < 0.55) {
    const f = furnitureFor(e.room)
    const spot = pick(f.breaks)
    if (!spot) return
    e.behavior = 'break'
    e.behaviorUntil = 5 + Math.random() * 6
    walkPath(e, nav, spot[0], spot[1], () => {
      e.activity = 'break'
      say(e, BREAK_LINES, 0.6)
    })
  } else {
    // Wander to a stroll spot and back
    const f = furnitureFor(e.room)
    const spot = pick(f.strolls)
    if (!spot) return
    e.behavior = 'stroll'
    e.behaviorUntil = 5 + Math.random() * 5
    walkPath(e, nav, spot[0], spot[1], () => {
      e.activity = 'stand'
    })
  }
}

function behaviorIdle(e: SimEmployee, nav: NavGrid | undefined): void {
  if (e.behavior === 'break' || e.behavior === 'stroll' || e.behavior === 'chat') {
    if (e.behaviorUntil === 0) endBehavior(e, nav, homeActivityFor(e))
    return
  }
  if (e._nextWander > 0) return
  e._nextWander = 6 + Math.random() * 10

  const f = furnitureFor(e.room)
  const spot = pick(Math.random() < 0.5 ? f.strolls : f.breaks)
  if (!spot) return
  e.behavior = 'stroll'
  e.behaviorUntil = 6 + Math.random() * 8
  walkPath(e, nav, spot[0], spot[1], () => {
    e.activity = 'stand'
  })
}

function behaviorMeeting(e: SimEmployee, nav: NavGrid | undefined): void {
  // Seat assignments: front pair faces s (sitting 'sit_s'), back pair faces n.
  if (e.behavior === 'seated') return
  const seat = MEETING_SEATS.get(e.id)
  if (!seat) {
    // Late joiners stand by the table (open floor south of it).
    if (e._nextWander > 0) return
    e._nextWander = 8
    walkPath(e, nav, 6.2, 29.9, () => {
      e.activity = 'stand'
      e.behavior = 'seated-stand'
      setFacing(e, seatDx(e), 1)
    })
    return
  }
  e.behavior = 'seated'
  e.behaviorUntil = 0
  walkPath(e, nav, seat[0], seat[1], () => {
    const target = { x: seat[0], y: seat[1] + (seat[2] === 's' ? 1.6 : -1.6) }
    setFacing(e, 0, seat[2] === 's' ? 1 : -1)
    e.activity = 'sit'
    // Slide onto the chair (short straight move, then sit pose)
    e.moving = {
      fromX: e.pos.x,
      fromY: e.pos.y,
      toX: target.x,
      toY: seat[1] + (seat[2] === 's' ? 0.45 : -0.45),
      start: 0,
      dur: 420,
      after: () => {
        e.activity = 'sit'
      },
    }
  })
}

/**
 * Meeting seat map: employee id → [global x, global y, facing].
 * Calibrated against the meeting-room art via object-density probing:
 * the table spans local i 2.4–8.6 / j 0.4–7.4, painted chairs hug local
 * j≈0 (north, facing s) and j≈8 (south, facing n). Room origin (0,20).
 * Exported for the nav-calibration view.
 */
export const MEETING_SEATS_EXPORT: [string, number, number, 's' | 'n'][] = [
  ['emp_010', 4.02, 20.0, 's'],
  ['emp_011', 6.42, 20.0, 's'],
  ['emp_015', 4.02, 28.0, 'n'],
  ['emp_016', 6.42, 28.0, 'n'],
]

const MEETING_SEATS = new Map(MEETING_SEATS_EXPORT.map(([id, x, y, f]) => [id, [x, y, f] as [number, number, 's' | 'n']]))

/* ── Chats ───────────────────────────────────────────────────────────── */

const chatPairs = new Map<string, string>() // a.id -> b.id

function updateChats(
  employees: SimEmployee[],
  nav: NavGrid | undefined,
  dt: number,
  _speed: number,
): void {
  void dt
  // Expire finished chats
  for (const [aid, bid] of chatPairs) {
    const a = employees.find((x) => x.id === aid)
    const b = employees.find((x) => x.id === bid)
    if (!a || !b || a.behavior !== 'chat' || b.behavior !== 'chat') {
      chatPairs.delete(aid)
      if (a && a.behavior === 'chat') endBehavior(a, nav, homeActivityFor(a))
      if (b && b.behavior === 'chat') endBehavior(b, nav, homeActivityFor(b))
    }
  }

  // Start new chats between people who are standing around in the same room.
  for (const a of employees) {
    if (!canChat(a)) continue
    const b = employees.find(
      (x) => x !== a && x.room === a.room && canChat(x) && !chatPairs.has(x.id),
    )
    if (!b) continue

    // Meet halfway between them.
    const mx = (a.pos.x + b.pos.x) / 2
    const my = (a.pos.y + b.pos.y) / 2
    const dur = 6 + Math.random() * 8
    const line = CHAT_LINES[Math.floor(Math.random() * CHAT_LINES.length)] ?? '…'
    chatPairs.set(a.id, b.id)
    a.behavior = 'chat'
    a.behaviorUntil = dur
    a.chatWith = b.id
    b.behavior = 'chat'
    b.behaviorUntil = dur
    b.chatWith = a.id
    walkPath(a, nav, mx, my, () => {
      a.activity = 'chat'
      faceEachOther(a, b)
      say(a, [line], 0.8)
    })
    walkPath(b, nav, mx + 0.35, my + 0.35, () => {
      b.activity = 'chat'
      faceEachOther(b, a)
      say(b, [line], 0.8)
    })
    break // one new chat per tick
  }
}

function canChat(e: SimEmployee): boolean {
  return (
    !e.path &&
    !e.moving &&
    (e.behavior === null || e.behavior === 'stroll' || e.behavior === 'break') &&
    e.fsm !== 'blocked' &&
    e.activity !== 'sit' &&
    e.activity !== 'desk' &&
    e.activity !== 'walk'
  )
}

function faceEachOther(a: SimEmployee, b: SimEmployee): void {
  setFacing(a, b.pos.x - a.pos.x, b.pos.y - a.pos.y)
}

/* ── Helpers ─────────────────────────────────────────────────────────── */

function homeTile(e: SimEmployee): { x: number; y: number } {
  return { x: Math.round(e.at[0]), y: Math.round(e.at[1]) }
}

function homeActivityFor(e: SimEmployee): Activity {
  if (e.fsm === 'meeting') return 'sit'
  if (e.fsm === 'working') return 'desk'
  return 'stand'
}

/** Return to the home anchor and resume the fsm-appropriate activity. */
export function endBehavior(e: SimEmployee, nav: NavGrid | undefined, activity: Activity): void {
  e.behavior = null
  e.behaviorUntil = 0
  e.chatWith = null
  e._wanderHome = null

  const home = homeTile(e)
  const dist = Math.hypot(home.x - e.pos.x, home.y - e.pos.y)
  if (dist < 0.4) {
    e.activity = activity
    return
  }
  walkPath(e, nav, home.x, home.y, () => {
    e.activity = activity
  })
}

function say(e: SimEmployee, lines: string[], chance = 0.7): void {
  if (Math.random() > chance) return
  const text = lines[Math.floor(Math.random() * lines.length)]
  if (!text) return
  e.bubble = { text, until: 2.6 + Math.random() * 1.6 } // seconds, ticked down
}

/** Tick all bubbles down by dt (call from the main loop). */
export function tickBubbles(employees: SimEmployee[], dt: number): void {
  for (const e of employees) {
    if (e.bubble) {
      e.bubble.until -= dt
      if (e.bubble.until <= 0) e.bubble = null
    }
  }
}

function nearTile(
  nav: NavGrid | undefined,
  center: { x: number; y: number },
  radius: number,
): { x: number; y: number } | null {
  if (!nav) return { x: center.x, y: center.y }
  for (let attempt = 0; attempt < 12; attempt++) {
    const x = Math.round(center.x + (Math.random() * 2 - 1) * radius)
    const y = Math.round(center.y + (Math.random() * 2 - 1) * radius)
    if (x >= 0 && y >= 0 && x < nav.w && y < nav.h && nav.blocked[y * nav.w + x] === 0) {
      return { x, y }
    }
  }
  return null
}

function pick<T>(arr: T[]): T | undefined {
  if (arr.length === 0) return undefined
  return arr[Math.floor(Math.random() * arr.length)]
}

function seatDx(_e: SimEmployee): number {
  return 0
}

/** Stop everything (used when the run pauses or an employee is removed). */
export function freezeAll(employees: SimEmployee[]): void {
  for (const e of employees) {
    stopWalking(e)
  }
}
