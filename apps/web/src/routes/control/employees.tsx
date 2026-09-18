/**
 * The employee table.
 *
 * Dense, sortable, default risk descending. Row click opens the same drawer
 * the office uses -- one component, so the two entry points cannot drift.
 *
 * `?focus=emp_017` scrolls to and highlights a row for two seconds, which is
 * what makes "View full activity" from the drawer land somewhere useful
 * rather than at the top of a list of twenty.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { formatMoney, formatTokens, roleLabel } from '@/lib/format'
import { useSim } from '@/stores/simStore'
import { useUi } from '@/stores/uiStore'
import type { EmployeePublic } from '@/lib/api'
import { EmptyState, RiskMeter, SkeletonRows, StatusChip, input, table } from '@/components/ui'

type SortKey = 'name' | 'team' | 'requests' | 'tokens' | 'cost' | 'risk'

export default function EmployeesRoute() {
  const [params] = useSearchParams()
  const focusId = params.get('focus')

  const employees = useSim((s) => s.employees)
  const avatars = useSim((s) => s.avatars)
  const selectEmployee = useUi((s) => s.selectEmployee)

  const [sort, setSort] = useState<SortKey>('risk')
  const [ascending, setAscending] = useState(false)
  const [team, setTeam] = useState('')
  const [minRisk, setMinRisk] = useState(0)

  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({})
  const [highlighted, setHighlighted] = useState<string | null>(focusId)

  useEffect(() => {
    if (!focusId) return
    rowRefs.current[focusId]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    setHighlighted(focusId)
    const timer = window.setTimeout(() => setHighlighted(null), 2000)
    return () => window.clearTimeout(timer)
  }, [focusId])

  const rows = useMemo(() => {
    const list = Object.values(employees).filter(
      (employee) =>
        (!team || employee.team === team) &&
        riskOf(employee, avatars) >= minRisk,
    )

    const direction = ascending ? 1 : -1
    return list.sort((a, b) => {
      switch (sort) {
        case 'name':
          return a.name.localeCompare(b.name) * direction
        case 'team':
          return a.team.localeCompare(b.team) * direction
        case 'requests':
          return (a.today.requests - b.today.requests) * direction
        case 'tokens':
          return (a.today.tokens - b.today.tokens) * direction
        case 'cost':
          return (a.today.cost_usd - b.today.cost_usd) * direction
        default:
          return (riskOf(a, avatars) - riskOf(b, avatars)) * direction
      }
    })
  }, [employees, avatars, team, minRisk, sort, ascending])

  const toggleSort = (key: SortKey) => {
    if (key === sort) setAscending(!ascending)
    else {
      setSort(key)
      setAscending(false)
    }
  }

  const loading = Object.keys(employees).length === 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <select
          className={input.select}
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          aria-label="Filter by team"
        >
          <option value="">All teams</option>
          {['payments', 'platform', 'frontend', 'data', 'exec'].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2">
          <span className="font-ui text-[11px] text-text-faint">Risk ≥</span>
          <input
            type="number"
            min={0}
            max={100}
            className={cn(input.text, 'w-20 font-mono tabular-nums')}
            value={minRisk}
            onChange={(e) => setMinRisk(Number(e.target.value))}
          />
        </label>

        <span className="ml-auto font-mono text-[11px] tabular-nums text-text-faint">
          {rows.length} employees
        </span>
      </div>

      <div className={table.wrapper}>
        <table className="w-full border-collapse">
          <thead className={table.head}>
            <tr>
              <SortableHeader label="Employee" active={sort === 'name'} ascending={ascending} onClick={() => toggleSort('name')} />
              <SortableHeader label="Team" active={sort === 'team'} ascending={ascending} onClick={() => toggleSort('team')} />
              <th scope="col" className={cn(table.th, 'w-28')}>
                Agent
              </th>
              <SortableHeader label="Requests" active={sort === 'requests'} ascending={ascending} onClick={() => toggleSort('requests')} className="w-24" />
              <SortableHeader label="Tokens" active={sort === 'tokens'} ascending={ascending} onClick={() => toggleSort('tokens')} className="w-24" />
              <SortableHeader label="Cost" active={sort === 'cost'} ascending={ascending} onClick={() => toggleSort('cost')} className="w-24" />
              <th scope="col" className={cn(table.th, 'w-32')}>
                A / R / B
              </th>
              <SortableHeader label="Risk" active={sort === 'risk'} ascending={ascending} onClick={() => toggleSort('risk')} className="w-44" />
              <th scope="col" className={cn(table.th, 'w-36')}>
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && <SkeletonRows rows={10} columns={9} />}

            {rows.map((employee) => {
              const risk = riskOf(employee, avatars)
              const overBudget = employee.today.cost_usd > employee.daily_budget_usd

              return (
                <tr
                  key={employee.id}
                  ref={(element) => {
                    rowRefs.current[employee.id] = element
                  }}
                  onClick={() => selectEmployee(employee.id)}
                  className={cn(
                    table.row,
                    highlighted === employee.id && 'bg-ink-600',
                  )}
                >
                  <td className={cn(table.cell, 'font-ui text-[13px]')}>
                    <span className="flex items-center gap-2">
                      <span className="h-5 w-5 rounded-xs bg-ink-700" aria-hidden />
                      <span>
                        {employee.name}
                        <span className="ml-1.5 font-ui text-[11px] text-text-faint">
                          {roleLabel(employee.role)}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className={cn(table.cell, 'text-text-dim')}>{employee.team}</td>
                  <td className={cn(table.cell, 'text-text-dim')}>{employee.agent_brand}</td>
                  <td className={table.cell}>{employee.today.requests}</td>
                  <td className={table.cell}>{formatTokens(employee.today.tokens)}</td>
                  <td className={cn(table.cell, overBudget ? 'text-block' : 'text-spend')}>
                    {formatMoney(employee.today.cost_usd)}
                  </td>
                  <td className={table.cell}>
                    <span className="text-allow">{employee.today.allowed}</span>
                    <span className="text-text-faint"> / </span>
                    <span className="text-review">{employee.today.review}</span>
                    <span className="text-text-faint"> / </span>
                    <span className="text-block">{employee.today.blocked}</span>
                  </td>
                  <td className={table.cell}>
                    <RiskMeter
                      score={risk}
                      lowConfidence={employee.risk_confidence === 'low'}
                      width="w-20"
                    />
                  </td>
                  <td className={table.cell}>
                    <StatusChip status={avatars[employee.id]?.fsm ?? employee.status} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>

        {!loading && rows.length === 0 && <EmptyState title="No employees in this run." />}
      </div>
    </div>
  )
}

function SortableHeader({
  label,
  active,
  ascending,
  onClick,
  className,
}: {
  label: string
  active: boolean
  ascending: boolean
  onClick: () => void
  className?: string
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (ascending ? 'ascending' : 'descending') : 'none'}
      onClick={onClick}
      className={cn(table.th, 'cursor-pointer select-none hover:text-text', className)}
    >
      {label}
      {active && <span className="ml-1">{ascending ? '↑' : '↓'}</span>}
    </th>
  )
}

function riskOf(
  employee: EmployeePublic,
  avatars: Record<string, { risk_score: number }>,
): number {
  return avatars[employee.id]?.risk_score ?? employee.risk_score
}
