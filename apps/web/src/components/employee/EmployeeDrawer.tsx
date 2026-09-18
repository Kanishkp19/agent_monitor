/**
 * The employee drawer.
 *
 * One component, shared by the office and the Control Center. Opening it from
 * an avatar and opening it from a table row must show the same thing, and the
 * only way to guarantee that is for there to be one of it.
 *
 * **It never shows `scenario_profile`.** Not because the component chooses not
 * to -- because the API does not return it and the type does not have the
 * field. The operator sees what the system inferred, which is the entire point
 * of the hidden-actor exercise.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { endpoints, type EmployeePublic, type RiskProfile } from '@/lib/api'
import { formatClock, formatMoney, formatTokens, roleLabel } from '@/lib/format'
import { cn } from '@/lib/cn'
import { useSim } from '@/stores/simStore'
import {
  Button,
  DecisionChip,
  Drawer,
  ErrorState,
  RiskMeter,
  SectionLabel,
  Skeleton,
  type Decision,
} from '@/components/ui'

interface Detail {
  employee: EmployeePublic
  risk: RiskProfile | null
  current_task: { id: string; title: string; repo: string; environment: string } | null
  recent_decisions: {
    seq: number
    sim_ts: number
    kind: string
    tool?: string
    resource?: string
    decision?: string
    task_id: string | null
  }[]
  seven_day: { requests: number; tokens: number; cost_usd: number }
}

export function EmployeeDrawer({
  employeeId,
  onClose,
}: {
  employeeId: string | null
  onClose: () => void
}) {
  const navigate = useNavigate()
  const run = useSim((s) => s.run)
  const cached = useSim((s) => (employeeId ? s.employees[employeeId] : undefined))

  const [detail, setDetail] = useState<Detail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!employeeId || !run) return
    let cancelled = false
    setLoading(true)
    setError(null)

    endpoints
      .employee(run.id, employeeId)
      .then((data) => !cancelled && setDetail(data as Detail))
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [employeeId, run])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!employeeId) return null

  // The header renders immediately from the store. Only the body waits.
  const employee = detail?.employee ?? cached
  const risk = detail?.risk

  return (
    <Drawer open onClose={onClose}>
      <div className="p-5">
        <header className="flex items-start justify-between">
          <div className="flex gap-3">
            <div className="h-10 w-10 shrink-0 rounded-sm bg-ink-700" aria-hidden />
            <div>
              <h2 className="font-ui text-[15px] font-semibold leading-6 text-text">
                {employee?.name ?? employeeId}
              </h2>
              <p className="font-ui text-[12px] text-text-dim">
                {employee ? `${roleLabel(employee.role)} · ${employee.team}` : ''}
              </p>
              {employee && (
                <p className="font-ui text-[11px] text-text-faint">
                  Agent: {roleLabel(employee.agent_brand)}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-faint hover:text-text"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {error && (
          <ErrorState
            title="Couldn't load this employee."
            detail={error}
            onRetry={() => setDetail(null)}
          />
        )}

        {!error && (
          <>
            <Section title="TODAY">
              {loading && !detail ? (
                <Skeleton className="h-16 w-full" />
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
                    <Metric label="Requests" value={employee?.today.requests ?? 0} />
                    <Metric
                      label="Tokens"
                      value={formatTokens(employee?.today.tokens ?? 0)}
                    />
                    <Metric
                      label="Cost"
                      value={formatMoney(employee?.today.cost_usd ?? 0)}
                      tone="spend"
                    />
                    <Metric label="Sessions" value={detail?.seven_day.requests ?? 0} />
                  </div>
                  <div className="mt-3 flex gap-4 font-mono text-[12px] tabular-nums">
                    <span className="text-allow">
                      Allowed {employee?.today.allowed ?? 0}
                    </span>
                    <span className="text-block">
                      Blocked {employee?.today.blocked ?? 0}
                    </span>
                    <span className="text-review">Review {employee?.today.review ?? 0}</span>
                  </div>
                </>
              )}
            </Section>

            <Section title="RISK">
              {loading && !risk ? (
                <Skeleton className="h-12 w-full" />
              ) : (
                <>
                  <RiskMeter
                    score={risk?.score ?? employee?.risk_score ?? 0}
                    lowConfidence={(risk?.confidence ?? employee?.risk_confidence) === 'low'}
                    sessions={risk?.sessions_observed}
                    width="w-40"
                  />
                  <ul className="mt-3 space-y-1">
                    {(risk?.top_factors ?? []).map((factor) => (
                      <li
                        key={factor.feature}
                        className="font-ui text-[12px] leading-5 text-text-dim"
                      >
                        · {factor.explanation}
                      </li>
                    ))}
                    {risk && risk.top_factors.length === 0 && (
                      <li className="font-ui text-[12px] text-text-faint">
                        Nothing unusual in this person&apos;s recent activity.
                      </li>
                    )}
                  </ul>
                  <div className="mt-3 flex justify-end">
                    <Button
                      variant="ghost"
                      onClick={() => navigate(`/control/risk?employee=${employeeId}`)}
                    >
                      Explain risk
                    </Button>
                  </div>
                </>
              )}
            </Section>

            <Section title="CURRENT TASK">
              {detail?.current_task ? (
                <>
                  <p className="font-ui text-[13px] text-text">
                    “{detail.current_task.title}”
                  </p>
                  <p className="mt-0.5 font-mono text-[12px] text-text-dim">
                    {detail.current_task.repo} · {detail.current_task.environment}
                  </p>
                  {employee?.status === 'awaiting_approval' && (
                    <p className="mt-2 font-ui text-[12px] text-review">
                      ⚠ Waiting for approval
                    </p>
                  )}
                  <div className="mt-2 flex justify-end">
                    <Button
                      variant="ghost"
                      onClick={() => navigate(`/live/${detail.current_task!.id}`)}
                    >
                      View request →
                    </Button>
                  </div>
                </>
              ) : (
                <p className="font-ui text-[12px] text-text-faint">Nothing in progress.</p>
              )}
            </Section>

            <Section title="RECENT DECISIONS">
              {loading && !detail ? (
                <Skeleton className="h-20 w-full" />
              ) : (detail?.recent_decisions.length ?? 0) === 0 ? (
                <p className="font-ui text-[12px] text-text-faint">
                  No governed activity yet.
                </p>
              ) : (
                <ul className="space-y-1">
                  {detail?.recent_decisions.slice(0, 10).map((decision) => (
                    <li
                      key={decision.seq}
                      onClick={() =>
                        decision.task_id && navigate(`/live/${decision.task_id}`)
                      }
                      className="flex cursor-pointer items-center gap-2 rounded-xs px-1 py-0.5 hover:bg-ink-700/60"
                    >
                      <span className="font-mono text-[11px] tabular-nums text-text-faint">
                        {formatClock(decision.sim_ts)}
                      </span>
                      <span className="flex-1 truncate font-mono text-[12px] text-text-dim">
                        {decision.tool ?? decision.kind} {decision.resource ?? ''}
                      </span>
                      {decision.decision && (
                        <DecisionChip decision={decision.decision as Decision} />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <div className="mt-4 border-t border-line pt-4">
              <Button
                variant="secondary"
                className="w-full justify-center"
                onClick={() => navigate(`/control/employees?focus=${employeeId}`)}
              >
                View full activity
              </Button>
            </div>
          </>
        )}
      </div>
    </Drawer>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-4 border-t border-line pt-4">
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string
  value: string | number
  tone?: 'spend'
}) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="font-ui text-[11px] text-text-faint">{label}</span>
      <span
        className={cn(
          'font-mono text-[13px] tabular-nums',
          tone === 'spend' ? 'text-spend' : 'text-text',
        )}
      >
        {value}
      </span>
    </div>
  )
}
