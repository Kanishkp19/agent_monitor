/**
 * The Policy Lab.
 *
 * Write a rule, run it against the last N hours of recorded telemetry, see
 * what it would have done. `docs/01-PRD.md` states the problem it solves
 * exactly: the security lead cannot pilot a policy without risking real
 * engineers' work.
 *
 * The number that matters is **"would block work that previously succeeded"**.
 * Everything else is context; that one is the false-positive proxy, and a rule
 * scoring high on it is a rule that will generate tickets.
 *
 * Nothing here is enforced. Drafts are never evaluated by live gates -- that
 * is a property of the storage flag, not a promise made by this screen.
 */

import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { ApiError, endpoints, type Policy } from '@/lib/api'
import { formatDelta, formatPercent, roleLabel } from '@/lib/format'
import { useSim } from '@/stores/simStore'
import { useUi } from '@/stores/uiStore'
import {
  Button,
  EmptyState,
  Panel,
  PanelHeader,
  Segmented,
  Skeleton,
  input,
  table,
} from '@/components/ui'

interface LabResult {
  window: { from_seq: number; to_seq: number; sim_hours: number }
  decisions_replayed: number
  requests_affected: number
  requests_affected_pct: number
  projected_spend_delta_usd: number
  projected_savings_pct: number
  newly_blocked_previously_succeeded: number
  newly_blocked_previously_blocked: number
  extra_approvals_per_day: number
  affected_by_role: { role: string; count: number }[]
  sample_affected: {
    task_id: string
    employee_id: string
    role: string
    tool_or_task_type: string
    was: string
    would_be: string
  }[]
  duration_ms: number
}

const SHOWCASE = {
  name: 'Interns may not use advanced models for low-complexity tasks',
  gate: 1 as const,
  effect: 'allow' as const,
  priority: 95,
  route_override: 'trivial',
  message: 'Routed to the standard model for low-complexity work.',
  when: {
    all: [
      { field: 'actor.role', op: 'eq', value: 'engineering_intern' },
      { field: 'request.complexity', op: 'in', value: ['trivial', 'standard'] },
      { field: 'request.routed_model', op: 'contains', value: 'sonnet' },
    ],
  },
}

export default function PolicyLabRoute() {
  const navigate = useNavigate()
  const location = useLocation()
  const run = useSim((s) => s.run)
  const nameOf = useSim((s) => s.nameOf)
  const toast = useUi((s) => s.toast)

  const incoming = (location.state as { draft?: Policy } | null)?.draft

  const [name, setName] = useState(incoming?.name ?? SHOWCASE.name)
  const [gate, setGate] = useState<1 | 2>((incoming?.gate as 1 | 2) ?? SHOWCASE.gate)
  const [effect, setEffect] = useState(incoming?.effect ?? SHOWCASE.effect)
  const [priority, setPriority] = useState(incoming?.priority ?? SHOWCASE.priority)
  const [conditionText, setConditionText] = useState(
    JSON.stringify(incoming?.when ?? SHOWCASE.when, null, 2),
  )
  const [windowHours, setWindowHours] = useState(24)

  const [result, setResult] = useState<LabResult | null>(null)
  const [running, setRunning] = useState(false)
  const [validation, setValidation] = useState<string | null>(null)

  useEffect(() => {
    setResult(null)
  }, [conditionText, gate])

  const simulate = async () => {
    if (!run) return

    let when: unknown
    try {
      when = JSON.parse(conditionText)
    } catch (e) {
      setValidation(`Not valid JSON: ${(e as Error).message}`)
      return
    }

    // Validate before simulating. Sending an invalid draft would produce a
    // 400 from the replay endpoint that says less about the mistake than the
    // validator does.
    try {
      await endpoints.validatePolicy(when, gate)
      setValidation(null)
    } catch (e) {
      const error = e as ApiError
      setValidation(`${error.field ? `${error.field} — ` : ''}${error.message}`)
      return
    }

    setRunning(true)
    try {
      const data = await endpoints.simulatePolicy({
        run_id: run.id,
        window_sim_hours: windowHours,
        draft_policy: {
          name,
          gate,
          effect,
          priority,
          is_draft: true,
          when,
          message: SHOWCASE.message,
          route_override: effect === 'allow' ? SHOWCASE.route_override : null,
          approver: effect === 'review' ? { role: 'manager', scope: 'team' } : null,
        },
      })
      setResult(data as unknown as LabResult)
    } catch (e) {
      toast('error', (e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const promote = async () => {
    try {
      await endpoints.promotePolicy({
        name,
        gate,
        effect,
        priority,
        is_draft: false,
        enabled: true,
        when: JSON.parse(conditionText) as Record<string, unknown>,
        message: SHOWCASE.message,
        route_override: effect === 'allow' ? SHOWCASE.route_override : null,
        approver: effect === 'review' ? { role: 'manager', scope: 'team' } : null,
      })
      toast('success', 'Promoted. Active on the next evaluation.')
      navigate('/control/policies')
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,420px)_1fr]">
      <Panel>
        <PanelHeader title="Draft policy" />
        <div className="space-y-4 p-4">
          <div>
            <label className={input.label} htmlFor="lab-name">
              Name
            </label>
            <input
              id="lab-name"
              className={input.text}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="flex flex-wrap gap-3">
            <Segmented
              value={gate}
              onChange={setGate}
              options={[
                { value: 1, label: 'Gate 1' },
                { value: 2, label: 'Gate 2' },
              ]}
            />
            <Segmented
              value={effect}
              onChange={setEffect}
              options={[
                { value: 'allow', label: 'allow' },
                { value: 'redact', label: 'redact', disabled: gate === 2 },
                { value: 'review', label: 'review' },
                { value: 'block', label: 'block' },
              ]}
            />
            <input
              type="number"
              min={0}
              max={999}
              aria-label="Priority"
              className={cn(input.text, 'w-20 font-mono tabular-nums')}
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
            />
          </div>

          <div>
            <label className={input.label} htmlFor="lab-condition">
              Condition
            </label>
            <textarea
              id="lab-condition"
              rows={14}
              spellCheck={false}
              aria-invalid={validation !== null}
              className={cn(
                input.text,
                'h-auto resize-y py-2 font-mono text-[12px] leading-5',
                validation && 'border-block shadow-[0_0_0_1px_var(--color-block)]',
              )}
              value={conditionText}
              onChange={(e) => setConditionText(e.target.value)}
            />
            {validation && <p className={input.error}>{validation}</p>}
          </div>

          <div>
            <span className={input.label}>Replay window</span>
            <Segmented
              value={windowHours}
              onChange={setWindowHours}
              options={[
                { value: 6, label: '6h' },
                { value: 24, label: '24h' },
                { value: 168, label: '7d' },
              ]}
            />
          </div>

          <Button
            variant="primary"
            className="w-full justify-center"
            loading={running}
            onClick={() => void simulate()}
          >
            Run against digital twin
          </Button>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Projected effect" />
        <div className="p-4">
          {running && (
            <div className="space-y-3">
              <p className="font-ui text-[13px] text-text-dim">Replaying decisions…</p>
              <Skeleton className="h-2 w-full" />
            </div>
          )}

          {!running && !result && (
            <EmptyState
              title="Write a condition and run it."
              hint="Nothing is enforced until you promote it. Drafts are never evaluated by live gates."
            />
          )}

          {!running && result && result.requests_affected === 0 && (
            <EmptyState
              title="This policy wouldn't have changed anything in the last 24 hours."
              hint="Try widening the replay window, or loosening the condition."
            />
          )}

          {!running && result && result.requests_affected > 0 && (
            <>
              <dl className="grid gap-y-2">
                <Row
                  label="Requests affected"
                  value={`${result.requests_affected}  (${formatPercent(
                    result.requests_affected_pct,
                  )})`}
                />
                <Row
                  label="Estimated savings"
                  value={`${formatDelta(result.projected_spend_delta_usd)}  (${formatPercent(
                    result.projected_savings_pct,
                  )})`}
                  tone={result.projected_spend_delta_usd < 0 ? 'spend' : undefined}
                />
                <Row
                  label="Would block work that previously succeeded"
                  value={String(result.newly_blocked_previously_succeeded)}
                  tone={result.newly_blocked_previously_succeeded > 0 ? 'block' : undefined}
                />
                <Row
                  label="Extra approvals per day"
                  value={String(result.extra_approvals_per_day)}
                  tone={result.extra_approvals_per_day > 10 ? 'review' : undefined}
                />
                <Row
                  label="Decisions replayed"
                  value={`${result.decisions_replayed.toLocaleString()} in ${result.duration_ms}ms`}
                />
              </dl>

              {result.affected_by_role.length > 0 && (
                <section className="mt-5 border-t border-line pt-4">
                  <h4 className="font-ui text-[11px] font-medium text-text-faint">
                    AFFECTED BY ROLE
                  </h4>
                  <ul className="mt-2 space-y-1.5">
                    {result.affected_by_role.map((row) => (
                      <li key={row.role} className="flex items-center gap-3">
                        <span className="w-32 font-ui text-[12px] text-text-dim">
                          {roleLabel(row.role)}
                        </span>
                        <div className="h-2 flex-1 overflow-hidden rounded-xs bg-ink-700">
                          <div
                            className="h-full rounded-xs bg-shield"
                            style={{
                              width: `${
                                (row.count / result.requests_affected) * 100
                              }%`,
                            }}
                          />
                        </div>
                        <span className="w-10 text-right font-mono text-[12px] tabular-nums text-text">
                          {row.count}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {result.sample_affected.length > 0 && (
                <section className="mt-5 border-t border-line pt-4">
                  <h4 className="font-ui text-[11px] font-medium text-text-faint">
                    SAMPLE ({result.sample_affected.length} of {result.requests_affected})
                  </h4>
                  <table className="mt-2 w-full border-collapse">
                    <tbody>
                      {result.sample_affected.map((row) => (
                        <tr
                          key={row.task_id}
                          onClick={() => navigate(`/live/${row.task_id}`)}
                          className={table.row}
                        >
                          <td className={table.cellDense}>{nameOf(row.employee_id)}</td>
                          <td className={cn(table.cellDense, 'text-text-dim')}>
                            {row.tool_or_task_type}
                          </td>
                          <td className={cn(table.cellDense, 'text-text-faint')}>
                            {row.was} → {row.would_be}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}

              <div className="mt-5 flex justify-end border-t border-line pt-4">
                <Button variant="primary" onClick={() => void promote()}>
                  Promote to active policy
                </Button>
              </div>
            </>
          )}
        </div>
      </Panel>
    </div>
  )
}

function Row({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'spend' | 'block' | 'review'
}) {
  return (
    <div className="flex items-baseline justify-between gap-6">
      <dt className="font-ui text-[13px] text-text-dim">{label}</dt>
      <dd
        className={cn(
          'font-mono text-[13px] tabular-nums font-medium',
          tone === 'spend'
            ? 'text-spend'
            : tone === 'block'
              ? 'text-block'
              : tone === 'review'
                ? 'text-review'
                : 'text-text',
        )}
      >
        {value}
      </dd>
    </div>
  )
}
