/**
 * The executive overview.
 *
 * `docs/01-PRD.md` quotes the CTO: "Don't show me tokens. Show me what it cost
 * and what it stopped." Six stats, two breakdowns, and a named-evidence panel
 * answering "why is Payments high?" -- because a risk level nobody can
 * interrogate is a number, not an answer.
 *
 * The layout adapts to `viewAs`. A manager sees their team; an engineer sees
 * themselves. That is a view filter, not a permission -- v1 has no auth.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import { cn } from '@/lib/cn'
import { endpoints, type Incident, type MetricsSummary, type RiskProfile } from '@/lib/api'
import { formatMoney } from '@/lib/format'
import { riskColor } from '@/lib/risk'
import { useSim } from '@/stores/simStore'
import { useUi } from '@/stores/uiStore'
import {
  Button,
  EmptyState,
  ErrorState,
  Panel,
  PanelHeader,
  RiskMeter,
  Skeleton,
  StatCard,
} from '@/components/ui'

export default function ControlOverviewRoute() {
  const navigate = useNavigate()
  const run = useSim((s) => s.run)
  const nameOf = useSim((s) => s.nameOf)
  const viewAs = useUi((s) => s.viewAs)

  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [leaderboard, setLeaderboard] = useState<RiskProfile[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    if (!run) return
    try {
      setError(null)
      const [summary, openIncidents, risk] = await Promise.all([
        endpoints.metrics(run.id, viewAs === 'ceo' ? 'exec' : 'security'),
        endpoints.incidents(run.id),
        endpoints.riskLeaderboard(run.id),
      ])
      setMetrics(summary)
      setIncidents(openIncidents)
      setLeaderboard(risk)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    void load()
    const timer = window.setInterval(() => void load(), 10_000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, viewAs])

  if (error) {
    return <ErrorState title="Couldn't load the overview." detail={error} onRetry={load} />
  }

  if (!metrics) {
    return (
      <div className="grid grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[76px] rounded-md" />
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard value={metrics.employees_enabled} label="AI-enabled employees" />
        <StatCard
          value={metrics.requests_today.toLocaleString()}
          label="Agent requests today"
        />
        <StatCard
          value={formatMoney(metrics.spend_today_usd)}
          label="Spend today"
          tone="spend"
          onClick={() => navigate('/control/costs')}
        />
        <StatCard
          value={formatMoney(metrics.waste_prevented_usd)}
          label="Waste prevented"
          tone="spend"
          onClick={() => navigate('/control/costs?view=waste')}
        />
        <StatCard
          value={metrics.blocked_actions}
          label="Blocked actions"
          tone="block"
          onClick={() => navigate('/live?decision=block')}
        />
        <StatCard
          value={metrics.approvals_today}
          label="Approvals"
          tone="review"
          onClick={() => navigate('/approvals')}
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="AI spend by team" />
          <div className="p-4">
            {metrics.spend_by_team.length === 0 ? (
              <EmptyState title="No spend recorded yet." />
            ) : (
              <BarList
                rows={metrics.spend_by_team.map((row) => ({
                  key: row.team,
                  value: row.usd,
                  label: formatMoney(row.usd),
                }))}
                color="var(--color-spend)"
              />
            )}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Risk by team" />
          <div className="p-4">
            <ul className="space-y-2">
              {metrics.risk_by_team.map((row) => (
                <li
                  key={row.team}
                  onClick={() => navigate(`/control/risk?team=${row.team}`)}
                  className="flex cursor-pointer items-center justify-between rounded-xs px-1 py-1 hover:bg-ink-700/60"
                >
                  <span className="font-ui text-[13px] text-text">{row.team}</span>
                  <span className="flex items-center gap-3">
                    <span
                      className="font-mono text-[11px] font-medium tracking-[0.04em]"
                      style={{ color: riskColor(row.score) }}
                    >
                      {row.level.toUpperCase()}
                    </span>
                    <ChevronRight className="h-3.5 w-3.5 text-text-faint" />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      </div>

      {metrics.why_high.team && metrics.why_high.reasons.length > 0 && (
        <Panel>
          <PanelHeader title={`Why is ${metrics.why_high.team} high?`} />
          <div className="p-4">
            <ul className="space-y-1">
              {metrics.why_high.reasons.map((reason) => (
                <li key={reason} className="font-ui text-[13px] leading-5 text-text-dim">
                  · {reason}
                </li>
              ))}
            </ul>
            <div className="mt-3 flex justify-end">
              <Button
                variant="secondary"
                onClick={() => navigate(`/control/risk?team=${metrics.why_high.team}`)}
              >
                Investigate {metrics.why_high.team} →
              </Button>
            </div>
          </div>
        </Panel>
      )}

      {viewAs !== 'ceo' && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel>
            <PanelHeader title={`Open incidents (${incidents.length})`} />
            <div className="p-4">
              {incidents.length === 0 ? (
                <EmptyState title="No incidents. That's the goal." />
              ) : (
                <ul className="space-y-2">
                  {incidents.slice(0, 5).map((incident) => (
                    <li
                      key={incident.id}
                      onClick={() => navigate('/control/incidents')}
                      className="flex cursor-pointer items-center gap-2 rounded-xs px-1 py-1 hover:bg-ink-700/60"
                    >
                      <span
                        className="h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: riskColor(incident.score) }}
                      />
                      <span className="font-ui text-[13px] text-text">
                        {nameOf(incident.employee_id)}
                      </span>
                      <span className="flex-1 truncate font-ui text-[12px] text-text-dim">
                        {incident.summary}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Risk leaderboard" />
            <div className="p-4">
              {leaderboard.length === 0 ? (
                <EmptyState
                  title="Not enough activity to score anyone yet."
                  hint="Risk needs 20 sessions per person. Fast-forward a week."
                />
              ) : (
                <ul className="space-y-2">
                  {leaderboard.slice(0, 6).map((profile) => (
                    <li
                      key={profile.employee_id}
                      onClick={() =>
                        navigate(`/control/risk?employee=${profile.employee_id}`)
                      }
                      className="flex cursor-pointer items-center justify-between rounded-xs px-1 py-1 hover:bg-ink-700/60"
                    >
                      <span className="font-ui text-[13px] text-text">
                        {nameOf(profile.employee_id)}
                      </span>
                      <RiskMeter
                        score={profile.score}
                        lowConfidence={profile.confidence === 'low'}
                        width="w-20"
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>
        </div>
      )}

      <Panel>
        <PanelHeader title="7-day trend" />
        <div className="grid grid-cols-3 gap-6 p-4">
          <Sparkline
            label="spend"
            values={metrics.trend_7d.map((d) => d.spend_usd)}
            color="var(--color-spend)"
          />
          <Sparkline
            label="blocked"
            values={metrics.trend_7d.map((d) => d.blocked)}
            color="var(--color-block)"
          />
          <Sparkline
            label="approvals"
            values={metrics.trend_7d.map((d) => d.approvals)}
            color="var(--color-review)"
          />
        </div>
      </Panel>
    </div>
  )
}

export function BarList({
  rows,
  color,
}: {
  rows: { key: string; value: number; label: string }[]
  color: string
}) {
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <ul className="space-y-2">
      {rows.map((row) => (
        <li key={row.key} className="flex items-center gap-3">
          <span className="w-20 shrink-0 font-ui text-[12px] text-text-dim">{row.key}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-xs bg-ink-700">
            <div
              className="h-full rounded-xs"
              style={{ width: `${(row.value / max) * 100}%`, background: color }}
            />
          </div>
          <span className="w-16 shrink-0 text-right font-mono text-[12px] tabular-nums text-text">
            {row.label}
          </span>
        </li>
      ))}
    </ul>
  )
}

/**
 * A sparkline in text blocks rather than SVG.
 *
 * Seven points do not need a charting library, and `▁▂▃▅▆▇█` reads at a glance
 * in a row of stats. Recharts is reserved for the cost view, where the shape
 * actually carries information.
 */
function Sparkline({
  label,
  values,
  color,
}: {
  label: string
  values: number[]
  color: string
}) {
  const blocks = '▁▂▃▅▆▇█'
  const max = Math.max(...values, 1)
  const spark = values
    .map((value) => blocks[Math.min(blocks.length - 1, Math.floor((value / max) * 6))])
    .join('')

  return (
    <div>
      <p className="font-ui text-[11px] text-text-faint">{label}</p>
      <p className={cn('mt-1 font-mono text-[16px] leading-5')} style={{ color }}>
        {spark || '—'}
      </p>
    </div>
  )
}
