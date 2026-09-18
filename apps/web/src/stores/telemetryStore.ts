/**
 * The event stream. WebSocket-owned.
 *
 * `docs/DESIGN.md` section 11: REST and WS never write to the same store
 * slice. `simStore` holds run and employee state and is REST-owned; this holds
 * the event stream and is WS-owned. Nothing reconciles them, because they
 * never overlap -- which is why there is no reconciliation bug to have.
 *
 * Two capacity rules keep a 200 event/second stream renderable:
 *
 * - The buffer is a **ring capped at 2,000**. Oldest evicted. A tab left open
 *   overnight uses the same memory as one opened a minute ago.
 * - `officeQueue` is a **separate, smaller slice** holding only the six events
 *   the canvas reacts to. The office pump drains that, not the whole stream,
 *   so it never walks 2,000 rows to find the four it cares about.
 */

import { create } from 'zustand'

import { OFFICE_EVENT_TYPES, type EventEnvelope } from '@/types/generated'

const BUFFER_CAP = 2_000
const OFFICE_QUEUE_CAP = 400
const LOG_CAP = 200

interface TelemetryState {
  events: EventEnvelope[]
  officeQueue: EventEnvelope[]
  log: EventEnvelope[]
  lastSeq: number
  connected: boolean
  paused: boolean
  bufferedWhilePaused: EventEnvelope[]

  ingest: (events: EventEnvelope[]) => void
  drainOfficeQueue: (max: number) => EventEnvelope[]
  clearOfficeQueue: () => void
  setConnected: (connected: boolean) => void
  setPaused: (paused: boolean) => void
  resume: () => void
  setLastSeq: (seq: number) => void
  reset: () => void
}

export const useTelemetry = create<TelemetryState>((set, get) => ({
  events: [],
  officeQueue: [],
  log: [],
  lastSeq: 0,
  connected: false,
  paused: false,
  bufferedWhilePaused: [],

  ingest: (incoming) => {
    if (incoming.length === 0) return
    const state = get()

    // Pausing freezes the view, not the stream. Events accumulate and flush
    // on resume with a count, so a reader never silently misses a block.
    if (state.paused) {
      set({
        bufferedWhilePaused: [...state.bufferedWhilePaused, ...incoming].slice(-BUFFER_CAP),
        lastSeq: Math.max(state.lastSeq, incoming[incoming.length - 1]?.detail.seq ?? 0),
      })
      return
    }

    const officeRelevant = incoming.filter((e) => OFFICE_EVENT_TYPES.has(e.detail_type))

    set({
      events: [...state.events, ...incoming].slice(-BUFFER_CAP),
      officeQueue: [...state.officeQueue, ...officeRelevant].slice(-OFFICE_QUEUE_CAP),
      log: [...state.log, ...incoming].slice(-LOG_CAP),
      lastSeq: Math.max(state.lastSeq, incoming[incoming.length - 1]?.detail.seq ?? 0),
    })
  },

  drainOfficeQueue: (max) => {
    const queue = get().officeQueue
    if (queue.length === 0) return []
    const taken = queue.slice(0, max)
    set({ officeQueue: queue.slice(max) })
    return taken
  },

  clearOfficeQueue: () => set({ officeQueue: [] }),

  setConnected: (connected) => set({ connected }),

  setPaused: (paused) => set({ paused }),

  resume: () => {
    const state = get()
    const buffered = state.bufferedWhilePaused
    const officeRelevant = buffered.filter((e) => OFFICE_EVENT_TYPES.has(e.detail_type))
    set({
      paused: false,
      bufferedWhilePaused: [],
      events: [...state.events, ...buffered].slice(-BUFFER_CAP),
      officeQueue: [...state.officeQueue, ...officeRelevant].slice(-OFFICE_QUEUE_CAP),
      log: [...state.log, ...buffered].slice(-LOG_CAP),
    })
  },

  setLastSeq: (seq) => set({ lastSeq: seq }),

  reset: () =>
    set({
      events: [],
      officeQueue: [],
      log: [],
      lastSeq: 0,
      bufferedWhilePaused: [],
      paused: false,
    }),
}))

/** Selector: how many events arrived while paused. Drives the resume label. */
export const selectBufferedCount = (state: TelemetryState): number =>
  state.bufferedWhilePaused.length
