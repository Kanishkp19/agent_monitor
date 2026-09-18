/**
 * WebSocket into Zustand.
 *
 * Three behaviours that matter more than they look:
 *
 * - **Reconnect resumes from `lastSeq`.** Not from a timestamp, and not from
 *   zero. The server replays exactly what was missed.
 * - **A gap over 500 events triggers a resnapshot** rather than a replay.
 *   Animating half a minute of catch-up would be a lie about what happened.
 * - **Backoff is exponential and capped.** A server restart must not turn
 *   twenty open tabs into a thundering herd.
 */

import type { EventEnvelope } from '@/types/generated'

export type WsFrameKind = 'event' | 'batch' | 'progress' | 'snapshot' | 'heartbeat'

export interface WsFrame {
  kind: WsFrameKind
  seq: number
  events?: EventEnvelope[]
  progress?: Record<string, number>
  gap?: number
  reason?: string
}

export interface StreamHandlers {
  onEvents: (events: EventEnvelope[]) => void
  onProgress: (progress: Record<string, number>) => void
  onResnapshot: (reason: string) => void
  onStatus: (connected: boolean) => void
  lastSeq: () => number
}

const MAX_BACKOFF_MS = 10_000
const INITIAL_BACKOFF_MS = 500
const PING_INTERVAL_MS = 20_000

export function connectStream(runId: string, handlers: StreamHandlers): () => void {
  let socket: WebSocket | null = null
  let backoff = INITIAL_BACKOFF_MS
  let retryTimer: number | undefined
  let pingTimer: number | undefined
  let closed = false

  const url = () => {
    const base = import.meta.env.VITE_WS_URL ?? '/ws/stream'
    const absolute = base.startsWith('ws')
      ? base
      : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}${base}`
    return `${absolute}?run_id=${runId}&since=${handlers.lastSeq()}`
  }

  const open = () => {
    if (closed) return
    socket = new WebSocket(url())

    socket.onopen = () => {
      backoff = INITIAL_BACKOFF_MS
      handlers.onStatus(true)
      // The server closes idle sockets; a periodic ping also surfaces a dead
      // connection promptly rather than at the next event, which during a
      // pause could be minutes.
      pingTimer = window.setInterval(() => socket?.send('ping'), PING_INTERVAL_MS)
    }

    socket.onmessage = (message) => {
      let frame: WsFrame
      try {
        frame = JSON.parse(message.data as string) as WsFrame
      } catch {
        return
      }

      switch (frame.kind) {
        case 'event':
        case 'batch':
          handlers.onEvents(frame.events ?? [])
          break
        case 'progress':
          handlers.onProgress(frame.progress ?? {})
          break
        case 'snapshot':
          handlers.onResnapshot(frame.reason ?? 'gap_too_large')
          break
        case 'heartbeat':
          break
      }
    }

    socket.onclose = () => {
      window.clearInterval(pingTimer)
      handlers.onStatus(false)
      if (closed) return
      retryTimer = window.setTimeout(open, backoff)
      backoff = Math.min(backoff * 2, MAX_BACKOFF_MS)
    }

    socket.onerror = () => socket?.close()
  }

  open()

  return () => {
    closed = true
    window.clearTimeout(retryTimer)
    window.clearInterval(pingTimer)
    socket?.close()
  }
}
