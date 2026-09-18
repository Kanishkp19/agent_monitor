/**
 * The avatar state machine.
 *
 * Transitions are driven **only** by events from the queue. There are exactly
 * two timed self-transitions, and both exist for a visual reason rather than a
 * logical one:
 *
 * - `BLOCKED -> IDLE` after four seconds of wall time, so the floor does not
 *   fill up with permanent red;
 * - `WALKING -> WORKING` on tween completion.
 *
 * `anomaly` is deliberately **not** a state. It is an overlay, so an employee
 * can be visibly working and flagged at the same time -- the ML flagging
 * someone who looks entirely normal is the most interesting thing the office
 * has to show, and folding it into the state would hide exactly that.
 */

import type { EventEnvelope } from '@/types/generated'

export type AvatarFsmState =
  | 'idle'
  | 'walking'
  | 'working'
  | 'waiting'
  | 'blocked'
  | 'meeting'

export const BLOCKED_HOLD_MS = 4_000
export const COMPLETED_HOLD_MS = 1_000

export interface FsmTransition {
  state: AvatarFsmState
  /** A one-shot visual: shake on a block, a spark on a redaction. */
  effect?: 'shake' | 'flash-green' | 'spark-redact' | 'bell'
  bubble?: string
  /** Auto-return to idle after this many milliseconds of wall time. */
  holdMs?: number
}

/**
 * What one event does to one avatar.
 *
 * Returns `null` when the event changes nothing visible -- most events do.
 * Only six of the eighteen types reach the canvas at all; the rest still
 * reach the Live Feed.
 */
export function transitionFor(
  current: AvatarFsmState,
  event: EventEnvelope,
): FsmTransition | null {
  const payload = event.detail.payload as Record<string, unknown>

  switch (event.detail_type) {
    case 'task.requested':
      return {
        state: 'working',
        bubble: truncateBubble(String(payload.title ?? '')),
      }

    case 'gate1.decision':
      switch (payload.decision) {
        case 'block':
          return { state: 'blocked', effect: 'shake', holdMs: BLOCKED_HOLD_MS }
        case 'review':
          return { state: 'waiting' }
        case 'redact':
          // A brief spark rather than a state change: the request continued,
          // it just went through with less in it.
          return { state: current, effect: 'spark-redact' }
        default:
          return null
      }

    case 'gate2.decision':
      switch (payload.decision) {
        case 'block':
          return { state: 'blocked', effect: 'shake', holdMs: BLOCKED_HOLD_MS }
        case 'review':
          return { state: 'waiting', effect: 'bell' }
        default:
          return null
      }

    case 'approval.decided':
      return String(payload.status ?? '').startsWith('approved')
        ? { state: 'working', effect: 'flash-green' }
        : { state: 'blocked', holdMs: BLOCKED_HOLD_MS }

    case 'task.completed':
      return { state: 'idle', holdMs: COMPLETED_HOLD_MS }

    case 'sim.meeting.started':
      return { state: 'meeting' }

    case 'sim.meeting.ended':
      return { state: 'idle' }

    default:
      return null
  }
}

/** Sprite animation key for a state and facing. */
export function animationFor(state: AvatarFsmState, facing: string): string {
  switch (state) {
    case 'walking':
      return `walk_${facing}`
    case 'working':
      return `type_${facing}`
    default:
      return `idle_${facing}`
  }
}

/** Max 28 characters, per the HUD spec -- longer does not fit the bubble. */
function truncateBubble(text: string): string {
  return text.length <= 28 ? text : `${text.slice(0, 27)}…`
}
