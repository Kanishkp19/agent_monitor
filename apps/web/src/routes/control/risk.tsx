/**
 * The risk screen: leaderboard, and why.
 *
 * Every factor is phrased by the API, not by this component -- the wording
 * lives in `risk/scoring.py` so the drawer, the explain endpoint and this
 * screen never describe the same signal three different ways.
 *
 * "Baseline vs now" is the section that makes a score arguable rather than
 * oracular: `tokens/session 4,100 ± 900 → 23,800` is a sentence someone can
 * disagree with, which is the point of an explanation.
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { endpoints, type RiskProfile } from '@/lib/api'
import { formatClock, roleLabel } from '@/lib/format'
import { riskColor } from '@/lib/risk'
import { useSim } from '@/stores/simStore'
import {
  Button,
  DecisionChip,
  EmptyState,
  ErrorState,
  Panel,
  PanelHeader,
  RiskMeter,
  SectionLabel,
  Skeleton,
  input,
  type Decision,
} from '@/components/ui'

type Explanation = RiskProfile & {
  baseline: { feature: string; mean: number; std: number; current: number }[]
  recent_contributors: { event_seq: number; sim_ts: number; kind: string; detail: string }[]
}

export default function RiskRoute() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const run = useSim((s) => s.run)
  const nameOf = useSim((s) => s.nameOf)
  const employees = useSim((s) => s.employees)

  const teamFilter = params.get('team') ?? ''
  const selectedId = params.get('employee')

  const [profiles, setProfiles] = useState<RiskProfile[] | null>(null)
  const [detail, setDetail] = useState<Explanation | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!run) return
    try {
      setError(null)
      setProfiles(await endpoints.riskLeaderboard(run.id, teamFilter || undefined))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [run, teamFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    if (!run || !selectedId) {
      setDetail(null)
      return
    }
    let cancelled = false
    setDetail(null)
    endpoints
      .explainRisk(run.id, selectedId)
      .then((data) => !cancelled && setDetail(data as Explanation))
      .catch(() => !cancelled && setDetail(null))
    return () => {
      cancelled = true
    }
  }, [run, selectedId])

  const select = (employeeId: string) => {
    const next = new URLSearchParams(params)
    next.set('employee', employeeId)
    setParams(next)
  }

  if (error) {
    return <ErrorState title="Couldn't load risk." detail={error} onRetry={load} />
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
      <Panel>
        <PanelHeader title="Risk leaderboard">
          <select
            className={input.select}
            value={teamFilter}
            onChange={(e) => {
              const next = new URLSearchParams(params)
              if (e.target.value) next.set('team', e.target.value)
              else next.delete('team')
              setParams(next)
            }}
            aria-label="Filter by team"
          >
            <option value="">All teams</option>
            {['payments', 'platform', 'frontend', 'data'].map((team) => (
              <option key={team} value={team}>
                {team}
              </option>
            ))}
          </select>
        </PanelHeader>

        <div className="p-3">
          {profiles === null && <Skeleton className="h-40 w-full" />}

          {profiles?.length === 0 && (
            <EmptyState
              title="Not enough activity to score anyone yet."
              hint="Risk needs 20 sessions per person. Run seed-history, or fast-forward a week."
            />
          )}

          <ul className="space-y-1">
            {profiles?.map((profile) => (
              <li
                key={profile.employee_id}
                onClick={() => select(profile.employee_id)}
                className={cn(
                  'flex cursor-pointer items-center gap-2 rounded-xs px-2 py-1.5',
                  profile.employee_id === selectedId
                    ? 'bg-ink-600 border-l-2 border-l-shield'
                    : 'hover:bg-ink-700/60',
                )}
              >
                <span
                  className="h-1.5 w-1.5 shrink-0 rounded-full"
                  style={{ background: riskColor(profile.score) }}
                />
                <span className="flex-1 truncate font-ui text-[13px] text-text">
                  {nameOf(profile.employee_id)}
                </span>
                <span className="font-mono text-[12px] tabular-nums text-text">
                  {profile.score}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </Panel>

      <Panel>
        {!selectedId ? (
          <EmptyState
            title="Select someone to see why."
            hint="Every factor is phrased in plain language by the API, not invented here."
          />
        ) : !detail ? (
          <div className="p-4">
            <Skeleton className="h-48 w-full" />
          </div>
        ) : (
          <div className="p-4">
            <header>
              <h2 className="font-ui text-[15px] font-semibold text-text">
                {nameOf(detail.employee_id)}
                <span className="ml-2 font-ui text-[12px] font-normal text-text-dim">
                  {roleLabel(employees[detail.employee_id]?.role ?? '')} ·{' '}
                  {employees[detail.employee_id]?.team ?? ''}
                </span>
              </h2>
              <div className="mt-2">
                <RiskMeter
                  score={detail.score}
                  lowConfidence={detail.confidence === 'low'}
                  sessions={detail.sessions_observed}
                  width="w-64"
                />
              </div>
              <p className="mt-1 font-mono text-[12px] tabular-nums text-text-dim">
                static {detail.static} · behavioural {detail.behavioural} · ml {detail.ml}
              </p>
            </header>

            <section className="mt-5 border-t border-line pt-4">
              <SectionLabel>TOP FACTORS</SectionLabel>
              <ol className="mt-2 space-y-1.5">
                {detail.top_factors.map((factor, index) => (
                  <li key={factor.feature} className="flex items-baseline gap-2">
                    <span className="font-mono text-[12px] text-text-faint">
                      {index + 1}.
                    </span>
                    <span className="flex-1 font-ui text-[13px] text-text">
                      {factor.explanation}
                    </span>
                    <span className="font-mono text-[12px] tabular-nums text-text-dim">
                      z = {factor.z.toFixed(1)}
                    </span>
                  </li>
                ))}
                {detail.top_factors.length === 0 && (
                  <li className="font-ui text-[12px] text-text-faint">
                    Nothing unusual in this person&apos;s recent activity.
                  </li>
                )}
              </ol>
            </section>

            {detail.baseline.length > 0 && (
              <section className="mt-5 border-t border-line pt-4">
                <SectionLabel>BASELINE vs NOW</SectionLabel>
                <table className="mt-2 w-full">
                  <tbody>
                    {detail.baseline.slice(0, 5).map((row) => (
                      <tr key={row.feature}>
                        <td className="py-0.5 font-ui text-[12px] text-text-dim">
                          {row.feature.replace(/_/g, ' ')}
                        </td>
                        <td className="py-0.5 text-right font-mono text-[12px] tabular-nums text-text-faint">
                          {round(row.mean)} ± {round(row.std)}
                        </td>
                        <td className="w-8 py-0.5 text-center font-mono text-[12px] text-text-faint">
                          →
                        </td>
                        <td className="w-20 py-0.5 text-right font-mono text-[12px] tabular-nums text-text">
                          {round(row.current)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            )}

            {detail.recent_contributors.length > 0 && (
              <section className="mt-5 border-t border-line pt-4">
                <SectionLabel>RECENT CONTRIBUTORS</SectionLabel>
                <ul className="mt-2 space-y-1">
                  {detail.recent_contributors.map((row) => (
                    <li key={row.event_seq} className="flex items-center gap-2">
                      <span className="font-mono text-[11px] tabular-nums text-text-faint">
                        {formatClock(row.sim_ts)}
                      </span>
                      <span className="flex-1 truncate font-mono text-[12px] text-text-dim">
                        {row.detail}
                      </span>
                      {decisionOf(row.detail) && (
                        <DecisionChip decision={decisionOf(row.detail)!} />
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <footer className="mt-5 flex gap-2 border-t border-line pt-4">
              <Button variant="secondary" onClick={() => navigate('/control/incidents')}>
                Open incidents
              </Button>
              <Button
                variant="ghost"
                onClick={() => navigate(`/live?employee=${detail.employee_id}`)}
              >
                View all activity
              </Button>
            </footer>
          </div>
        )}
      </Panel>
    </div>
  )
}

function round(value: number): string {
  if (Math.abs(value) >= 1000) return Math.round(value).toLocaleString()
  if (Math.abs(value) >= 10) return value.toFixed(1)
  return value.toFixed(2)
}

function decisionOf(detail: string): Decision | null {
  if (detail.includes('BLOCK')) return 'block'
  if (detail.includes('REVIEW')) return 'review'
  return null
}
