/**
 * Formatting, and the one place an event becomes a sentence.
 *
 * `describeEvent` is used by the system log rail and the Live Feed. Having one
 * implementation means the same event never reads two different ways on two
 * screens -- which is the sort of inconsistency nobody reports as a bug but
 * everybody quietly distrusts.
 *
 * Number rules from `docs/04-UI-UX-BRIEF.md` section 9: tokens humanise, money
 * shows two decimals under $100 and none above, percentages get one decimal
 * only below 10%.
 */

import type { EventEnvelope } from '@/types/generated'

export function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`
  return String(value)
}

export function formatMoney(value: number): string {
  if (value === 0) return '$0.00'
  if (Math.abs(value) >= 100) return `$${Math.round(value)}`
  if (Math.abs(value) < 0.01) return `$${value.toFixed(4)}`
  return `$${value.toFixed(2)}`
}

export function formatDelta(value: number): string {
  const sign = value < 0 ? '−' : '+'
  return `${sign}${formatMoney(Math.abs(value))}`
}

export function formatPercent(value: number): string {
  return value < 10 ? `${value.toFixed(1)}%` : `${Math.round(value)}%`
}

/** `Tue 09:21` -- the sim clock face. */
export function formatSimTime(simTs: number): string {
  const date = new Date(simTs * 1000)
  const day = date.toLocaleDateString('en-GB', { weekday: 'short', timeZone: 'UTC' })
  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')
  return `${day} ${hours}:${minutes}`
}

/** `09:21` -- log lines and table cells. */
export function formatClock(simTs: number): string {
  const date = new Date(simTs * 1000)
  return `${String(date.getUTCHours()).padStart(2, '0')}:${String(
    date.getUTCMinutes(),
  ).padStart(2, '0')}`
}

/** `4:12` -- an approval countdown. */
export function formatCountdown(seconds: number): string {
  if (seconds <= 0) return '0:00'
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`
}

// ──────────────────────────────────────────────────────────────────────
// Events
// ──────────────────────────────────────────────────────────────────────

export type Decision = 'allow' | 'redact' | 'review' | 'block'

export interface DescribedEvent {
  time: string
  /** Prose, in `text-dim`. */
  text: string
  /** The decision word, which takes its signal colour. */
  decision: Decision | null
  /** Short verb for the feed's WHAT column. */
  what: string
  who: string | null
  resource: string
  cost: number | null
  taskId: string | null
  gate: 'Gate 1' | 'Gate 2' | null
}

export function describeEvent(
  event: EventEnvelope,
  nameOf?: (employeeId: string) => string,
): DescribedEvent {
  const { detail } = event
  const payload = detail.payload as Record<string, unknown>
  const who = detail.employee_id ? (nameOf?.(detail.employee_id) ?? detail.employee_id) : null
  const base: DescribedEvent = {
    time: formatClock(detail.sim_ts),
    text: event.detail_type,
    decision: null,
    what: event.detail_type,
    who,
    resource: '',
    cost: null,
    taskId: detail.task_id,
    gate: null,
  }

  switch (event.detail_type) {
    case 'task.requested':
      return {
        ...base,
        what: 'request',
        resource: String(payload.repo ?? ''),
        text: `${who} started “${truncate(String(payload.title ?? ''), 34)}”`,
      }

    case 'gate1.decision': {
      const decision = payload.decision as Decision
      return {
        ...base,
        gate: 'Gate 1',
        what: 'request',
        decision,
        resource: String(payload.routed_model ?? ''),
        cost: Number(payload.est_cost_usd ?? 0),
        text: `${who}'s request — ${verbFor(decision)}`,
      }
    }

    case 'model.invoked':
      return {
        ...base,
        what: 'model',
        resource: shortModel(String(payload.model_id ?? '')),
        cost: Number(payload.cost_usd ?? 0),
        text: `${formatTokens(
          Number(payload.input_tokens ?? 0) + Number(payload.output_tokens ?? 0),
        )} tokens`,
      }

    case 'gate2.decision': {
      const decision = payload.decision as Decision
      return {
        ...base,
        gate: 'Gate 2',
        what: String(payload.tool ?? 'action'),
        decision,
        resource: String(payload.target_resource ?? ''),
        text: `${payload.tool} ${truncate(String(payload.target_resource ?? ''), 30)} — ${verbFor(
          decision,
        )}`,
      }
    }

    case 'approval.requested':
      return {
        ...base,
        what: 'approval',
        decision: 'review',
        resource: String(payload.approver_role ?? ''),
        text: `${who} needs approval — ${truncate(String(payload.reason ?? ''), 40)}`,
      }

    case 'approval.decided': {
      const status = String(payload.status ?? '')
      const approved = status.startsWith('approved')
      return {
        ...base,
        what: 'approval',
        decision: approved ? 'allow' : 'block',
        resource: status,
        text: approved ? 'Approved — the task is continuing' : `Approval ${status}`,
      }
    }

    case 'action.blocked':
      return {
        ...base,
        what: String(payload.tool ?? 'action'),
        decision: 'block',
        resource: String(payload.target_resource ?? ''),
        text: String(payload.message ?? 'Blocked by policy'),
      }

    case 'task.completed': {
      const status = String(payload.status ?? '')
      return {
        ...base,
        what: 'complete',
        cost: Number(payload.cost_usd ?? 0),
        resource: status,
        decision: status === 'completed' ? null : 'block',
        text: `${who} finished — ${status}`,
      }
    }

    case 'budget.exceeded':
      return {
        ...base,
        what: 'budget',
        decision: 'block',
        resource: `${formatMoney(Number(payload.spend_usd ?? 0))} / ${formatMoney(
          Number(payload.budget_usd ?? 0),
        )}`,
        text: `${who} hit their daily budget`,
      }

    case 'risk.updated':
      return {
        ...base,
        what: 'risk',
        resource: String(payload.score ?? ''),
        text: `${who}'s risk is now ${payload.score}`,
      }

    case 'incident.opened':
      return {
        ...base,
        what: 'incident',
        decision: 'block',
        resource: String(payload.detector ?? ''),
        text: `Incident opened — ${truncate(String(payload.summary ?? ''), 44)}`,
      }

    case 'sandbox.executed':
      return {
        ...base,
        what: String(payload.tool ?? 'executed'),
        resource: truncate(String(payload.output_preview ?? ''), 40),
        text: payload.ok ? 'Completed' : 'Failed',
        decision: payload.ok ? null : 'block',
      }

    default:
      return base
  }
}

function verbFor(decision: Decision): string {
  switch (decision) {
    case 'allow':
      return 'allowed'
    case 'redact':
      return 'secrets removed'
    case 'review':
      return 'held for approval'
    case 'block':
      return 'blocked'
  }
}

export function shortModel(modelId: string): string {
  if (modelId.includes('haiku')) return 'haiku'
  if (modelId.includes('sonnet')) return 'sonnet'
  if (modelId.includes('qwen')) return 'qwen'
  if (modelId.startsWith('mock:')) return `mock ${modelId.slice(5)}`
  return modelId
}

export function roleLabel(role: string): string {
  return role
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
