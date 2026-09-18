/**
 * Spend and waste.
 *
 * The waste number is the one people ask about, so its definition is printed
 * verbatim under the table -- taken from `docs/05-BACKEND-SCHEMA.md` section 4,
 * which is also where the API gets it. A figure on a demo screen that nobody
 * can define is a figure nobody believes.
 */

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { endpoints, type MetricsSummary } from '@/lib/api'
import { formatMoney, formatTokens } from '@/lib/format'
import { useSim } from '@/stores/simStore'
import {
  EmptyState,
  ErrorState,
  Panel,
  PanelHeader,
  Segmented,
  Skeleton,
  table,
} from '@/components/ui'
import { BarList } from './index'

type GroupBy = 'team' | 'employee' | 'model'

interface SpendSeries {
  group_by: string
  days: number
  series: { key: string; usd: number; tokens: number; waste_usd: number }[]
}

export default function CostsRoute() {
  const [params] = useSearchParams()
  const run = useSim((s) => s.run)
  const nameOf = useSim((s) => s.nameOf)

  const [groupBy, setGroupBy] = useState<GroupBy>('team')
  const [days, setDays] = useState(7)
  const [spend, setSpend] = useState<SpendSeries | null>(null)
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!run) return
    try {
      setError(null)
      const [series, summary] = await Promise.all([
        endpoints.spend(run.id, groupBy, days),
        endpoints.metrics(run.id),
      ])
      setSpend(series as SpendSeries)
      setMetrics(summary)
    } catch (e) {
      setError((e as Error).message)
    }
  }, [run, groupBy, days])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return <ErrorState title="Couldn't load spend." detail={error} onRetry={load} />
  }

  const trend = metrics?.trend_7d ?? []
  const wasteFocus = params.get('view') === 'waste'

  return (
    <div className="flex flex-col gap-5">
      <Panel>
        <PanelHeader title="Spend over time">
          <Segmented
            value={days}
            onChange={setDays}
            options={[
              { value: 7, label: '7 days' },
              { value: 30, label: '30 days' },
            ]}
          />
        </PanelHeader>
        <div className="h-56 p-4">
          {!metrics ? (
            <Skeleton className="h-full w-full" />
          ) : trend.length === 0 ? (
            <EmptyState title="No spend recorded yet." />
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend}>
                <CartesianGrid stroke="var(--color-line)" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="sim_date"
                  stroke="var(--color-text-faint)"
                  tick={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  stroke="var(--color-text-faint)"
                  tick={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(value: number) => `$${value}`}
                  width={48}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--color-ink-800)',
                    border: '1px solid var(--color-line)',
                    borderRadius: 6,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                  }}
                  labelStyle={{ color: 'var(--color-text-dim)' }}
                  formatter={(value: number) => [formatMoney(value), 'spend']}
                />
                <Area
                  type="monotone"
                  dataKey="spend_usd"
                  stroke="var(--color-spend)"
                  fill="var(--color-spend)"
                  fillOpacity={0.15}
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Breakdown">
          <Segmented
            value={groupBy}
            onChange={setGroupBy}
            options={[
              { value: 'team', label: 'By team' },
              { value: 'employee', label: 'By employee' },
              { value: 'model', label: 'By model' },
            ]}
          />
        </PanelHeader>
        <div className="p-4">
          {!spend ? (
            <Skeleton className="h-32 w-full" />
          ) : spend.series.length === 0 ? (
            <EmptyState title="No spend recorded yet." />
          ) : (
            <BarList
              rows={spend.series.map((row) => ({
                key: groupBy === 'employee' ? nameOf(row.key) : row.key,
                value: row.usd,
                label: formatMoney(row.usd),
              }))}
              color="var(--color-spend)"
            />
          )}
        </div>
      </Panel>

      <Panel className={wasteFocus ? 'border-line-strong' : undefined}>
        <PanelHeader title="Waste detail" />
        <div className="p-4">
          {!spend ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <>
              <table className="w-full border-collapse">
                <thead className={table.head}>
                  <tr>
                    <th scope="col" className={table.th}>
                      {groupBy}
                    </th>
                    <th scope="col" className={table.th}>
                      Tokens
                    </th>
                    <th scope="col" className={table.th}>
                      Spend
                    </th>
                    <th scope="col" className={table.th}>
                      Waste
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {spend.series.map((row) => (
                    <tr key={row.key} className="border-b border-line/60">
                      <td className={table.cell}>
                        {groupBy === 'employee' ? nameOf(row.key) : row.key}
                      </td>
                      <td className={table.cell}>{formatTokens(row.tokens)}</td>
                      <td className={`${table.cell} text-spend`}>{formatMoney(row.usd)}</td>
                      <td className={`${table.cell} text-block`}>
                        {formatMoney(row.waste_usd)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Verbatim from the schema doc, so the UI and the API can never
                  be accused of meaning different things by the same word. */}
              <p className="mt-4 max-w-[68ch] border-t border-line pt-3 font-ui text-[12px] leading-5 text-text-faint">
                <strong className="text-text-dim">Potential waste</strong> is total spend
                attributable to sessions that ended <code>blocked</code>,{' '}
                <code>denied</code>, <code>denied_timeout</code>, <code>failed</code>, or
                that triggered <code>pol_retry_loop_guard</code>.
              </p>
            </>
          )}
        </div>
      </Panel>
    </div>
  )
}
