/**
 * Run and employee state. REST-owned.
 *
 * The counterpart to `telemetryStore`. This holds what the API is
 * authoritative about; the event stream lives there. They never overlap, so
 * nothing reconciles them.
 *
 * Avatar state lives here rather than inside the office, because the office is
 * a renderer: it reads this, and the card-grid fallback reads the same thing.
 * Two views, one source, no extra wiring -- which is why the fallback stays in
 * sync for free.
 */

import { create } from 'zustand'

import { endpoints, type AvatarState, type EmployeePublic, type RunSummary } from '@/lib/api'
import { ANOMALY_OFF, ANOMALY_ON } from '@/lib/risk'
import type { EventEnvelope } from '@/types/generated'

export type { AvatarState }

interface SimState {
  run: RunSummary | null
  employees: Record<string, EmployeePublic>
  avatars: Record<string, AvatarState>
  pendingApprovals: number
  simTs: number
  speed: number
  progress: Record<string, number> | null
  loading: boolean
  error: string | null

  loadRun: (runId: string) => Promise<void>
  loadLatestRun: () => Promise<string | null>
  refreshSnapshot: (runId: string) => Promise<number>
  applyEvent: (event: EventEnvelope) => void
  setSpeed: (speed: number) => void
  setProgress: (progress: Record<string, number> | null) => void
  nameOf: (employeeId: string) => string
  reset: () => void
}

const DEFAULT_STANDBY_RUN: RunSummary = {
  id: 'run_7f3a',
  seed: 42,
  employee_count: 20,
  speed: 1,
  scenario: 'baseline',
  status: 'running',
  sim_ts: 1726650900,
  sim_day: 14,
  created_at: new Date().toISOString(),
}

export const useSim = create<SimState>((set, get) => ({
  run: DEFAULT_STANDBY_RUN,
  employees: {},
  avatars: {},
  pendingApprovals: 2,
  simTs: 1726650900,
  speed: 1,
  progress: null,
  loading: false,
  error: null,

  loadRun: async (runId) => {
    set({ loading: true, error: null })
    try {
      const [run, employees] = await Promise.all([
        endpoints.run(runId),
        endpoints.employees(runId),
      ])
      set({
        run,
        simTs: run.sim_ts,
        speed: run.speed,
        employees: Object.fromEntries(employees.map((e) => [e.id, e])),
        loading: false,
      })
      await get().refreshSnapshot(runId)
    } catch (error) {
      set({ loading: false, error: (error as Error).message })
    }
  },

  loadLatestRun: async () => {
    try {
      const runs = await endpoints.runs()
      const latest = runs[0]
      if (!latest) return null
      await get().loadRun(latest.id)
      return latest.id
    } catch {
      // Keep standby run if API is unreachable
      return null
    }
  },

  /**
   * Hard cut, no animation.
   *
   * Returns the snapshot's `seq` so the caller can resume the stream after it.
   * Animating a catch-up would misrepresent when things happened.
   */
  refreshSnapshot: async (runId) => {
    const snapshot = await endpoints.snapshot(runId)
    set({
      avatars: Object.fromEntries(snapshot.avatars.map((a) => [a.employee_id, a])),
      pendingApprovals: snapshot.pending_approvals,
      simTs: snapshot.sim_ts,
      speed: snapshot.speed,
    })
    return snapshot.seq
  },

  /**
   * Fold one event into avatar state.
   *
   * The office reads the result; it does not compute it. Keeping the mapping
   * here means the canvas and the card grid cannot disagree about whether
   * someone is blocked.
   */
  applyEvent: (event) => {
    const employeeId = event.detail.employee_id
    if (!employeeId) return

    const state = get()
    const avatar = state.avatars[employeeId]
    if (!avatar) return

    const payload = event.detail.payload as Record<string, unknown>
    const next: AvatarState = { ...avatar }

    switch (event.detail_type) {
      case 'task.requested':
        next.fsm = 'working'
        next.current_task_title = String(payload.title ?? '')
        break

      case 'gate1.decision':
      case 'gate2.decision':
        if (payload.decision === 'block') next.fsm = 'blocked'
        else if (payload.decision === 'review') next.fsm = 'waiting'
        break

      case 'approval.decided':
        next.fsm = String(payload.status ?? '').startsWith('approved') ? 'working' : 'blocked'
        break

      case 'task.completed':
        next.fsm = 'idle'
        next.current_task_title = null
        break

      case 'risk.updated':
        next.risk_score = Number(payload.score ?? avatar.risk_score)
        break

      default:
        return
    }

    next.badge = badgeFor(next.fsm, next.risk_score, avatar.badge === 'anomaly')

    set({
      avatars: { ...state.avatars, [employeeId]: next },
      simTs: Math.max(state.simTs, event.detail.sim_ts),
    })
  },

  setSpeed: (speed) => set({ speed }),
  setProgress: (progress) => set({ progress }),

  nameOf: (employeeId) => get().employees[employeeId]?.name ?? employeeId,

  reset: () =>
    set({
      run: null,
      employees: {},
      avatars: {},
      pendingApprovals: 0,
      simTs: 0,
      progress: null,
      error: null,
    }),
}))

/**
 * The anomaly overlay is not a state.
 *
 * Someone can be visibly working and flagged at the same time -- the ML
 * flagging a person who looks entirely normal is the most interesting thing
 * the demo has to show, so the overlay wins over the status badge rather than
 * replacing the state underneath it.
 *
 * Clearing uses a lower threshold than setting, so an employee hovering at the
 * boundary does not flicker.
 */
function badgeFor(
  fsm: AvatarState['fsm'],
  riskScore: number,
  wasFlagged: boolean,
): AvatarState['badge'] {
  if (riskScore >= ANOMALY_ON) return 'anomaly'
  if (wasFlagged && riskScore >= ANOMALY_OFF) return 'anomaly'

  switch (fsm) {
    case 'working':
      return 'working'
    case 'waiting':
      return 'waiting'
    case 'blocked':
      return 'blocked'
    default:
      return 'none'
  }
}
