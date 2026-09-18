/**
 * The Live Feed.
 *
 * The full governed event stream, filterable and pausable. Capacity is the
 * design constraint: 200 events/second has to stay readable, which means
 * virtualising the list, capping the buffer at 2,000, and suppressing the
 * row-flash above 40 events/second -- a table that strobes is a table nobody
 * reads.
 *
 * Pause freezes the view, not the stream. Events accumulate and flush on
 * resume with a count, so a reader never silently misses a block.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ListFilter, Pause, Play } from 'lucide-react'

import { cn } from '@/lib/cn'
import { describeEvent, formatClock, formatMoney, roleLabel } from '@/lib/format'
import { endpoints } from '@/lib/api'
import { useSim } from '@/stores/simStore'
import { selectBufferedCount, useTelemetry } from '@/stores/telemetryStore'
import {
  Button,
  DecisionChip,
  EmptyState,
  Panel,
  Segmented,
  Skeleton,
  input,
  table,
  type Decision,
} from '@/components/ui'
import type { EventEnvelope } from '@/types/generated'

const FLASH_SUPPRESS_RATE = 40
const ROW_HEIGHT = 30

interface Filters {
  employee: string
  team: string
  gate: 'all' | '1' | '2' | 'none'
  decision: string
  tool: string
  minRisk: number
  search: string
}

const EMPTY_FILTERS: Filters = {
  employee: '',
  team: '',
  gate: 'all',
  decision: '',
  tool: '',
  minRisk: 0,
  search: '',
}

export default function LiveFeedRoute() {
  const { taskId } = useParams()
  const navigate = useNavigate()

  const events = useTelemetry((s) => s.events)
  const paused = useTelemetry((s) => s.paused)
  const setPaused = useTelemetry((s) => s.setPaused)
  const resume = useTelemetry((s) => s.resume)
  const bufferedCount = useTelemetry(selectBufferedCount)

  const employees = useSim((s) => s.employees)
  const nameOf = useSim((s) => s.nameOf)

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [expanded, setExpanded] = useState<string | null>(taskId ?? null)

  const filtered = useMemo(
    () => events.filter((event) => matches(event, filters, employees)).slice().reverse(),
    [events, filters, employees],
  )

  const parentRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  })

  // Measured, not assumed: the flash is suppressed only when the stream is
  // genuinely fast enough for it to be noise.
  const rate = useEventRate(events)

  const hasFilters = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS)

  return (
    <div className="flex flex-col gap-4">
      <Panel>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <select
            className={input.select}
            value={filters.employee}
            onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
            aria-label="Filter by employee"
          >
            <option value="">All employees</option>
            {Object.values(employees).map((employee) => (
              <option key={employee.id} value={employee.id}>
                {employee.name}
              </option>
            ))}
          </select>

          <select
            className={input.select}
            value={filters.team}
            onChange={(e) => setFilters({ ...filters, team: e.target.value })}
            aria-label="Filter by team"
          >
            <option value="">All teams</option>
            {['payments', 'platform', 'frontend', 'data', 'exec'].map((team) => (
              <option key={team} value={team}>
                {team}
              </option>
            ))}
          </select>

          <Segmented
            value={filters.gate}
            onChange={(gate) => setFilters({ ...filters, gate })}
            options={[
              { value: 'all', label: 'All' },
              { value: '1', label: 'Gate 1' },
              { value: '2', label: 'Gate 2' },
              { value: 'none', label: 'Neither' },
            ]}
          />

          <select
            className={input.select}
            value={filters.decision}
            onChange={(e) => setFilters({ ...filters, decision: e.target.value })}
            aria-label="Filter by decision"
          >
            <option value="">All decisions</option>
            {['allow', 'redact', 'review', 'block'].map((decision) => (
              <option key={decision} value={decision}>
                {decision}
              </option>
            ))}
          </select>

          <select
            className={input.select}
            value={filters.tool}
            onChange={(e) => setFilters({ ...filters, tool: e.target.value })}
            aria-label="Filter by tool"
          >
            <option value="">All tools</option>
            {[
              'read_file',
              'edit_file',
              'run_tests',
              'git_commit',
              'git_push',
              'call_api',
              'deploy',
              'external_fetch',
            ].map((tool) => (
              <option key={tool} value={tool}>
                {tool}
              </option>
            ))}
          </select>

          <input
            className={cn(input.text, 'w-48')}
            placeholder="Search resource, policy, task…"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            aria-label="Search events"
          />

          <div className="flex-1" />

          <Button
            variant={paused ? 'primary' : 'secondary'}
            onClick={() => (paused ? resume() : setPaused(true))}
          >
            {paused ? (
              <>
                <Play className="h-3.5 w-3.5" />
                Resume{bufferedCount > 0 ? ` (${bufferedCount} new)` : ''}
              </>
            ) : (
              <>
                <Pause className="h-3.5 w-3.5" />
                Pause
              </>
            )}
          </Button>

          <span className="font-mono text-[11px] tabular-nums text-text-faint">
            {filtered.length.toLocaleString()} events
          </span>
        </div>
      </Panel>

      <div className={table.wrapper}>
        <table className="w-full border-collapse">
          <thead className={table.head}>
            <tr>
              <th scope="col" className={cn(table.th, 'w-14')}>
                Time
              </th>
              <th scope="col" className={cn(table.th, 'w-36')}>
                Who
              </th>
              <th scope="col" className={cn(table.th, 'w-20')}>
                Gate
              </th>
              <th scope="col" className={cn(table.th, 'w-28')}>
                What
              </th>
              <th scope="col" className={table.th}>
                Resource
              </th>
              <th scope="col" className={cn(table.th, 'w-24')}>
                Decision
              </th>
              <th scope="col" className={cn(table.th, 'w-20 text-right')}>
                Cost
              </th>
            </tr>
          </thead>
        </table>

        <div ref={parentRef} className="h-[calc(100vh-280px)] overflow-auto">
          {filtered.length === 0 ? (
            <EmptyState
              icon={ListFilter}
              title={
                hasFilters
                  ? 'No events match these filters.'
                  : 'No events yet. Start the simulation to see governed activity.'
              }
              hint={hasFilters ? undefined : 'Press ▶ REAL TIME in the header.'}
              action={
                hasFilters ? (
                  <Button variant="secondary" onClick={() => setFilters(EMPTY_FILTERS)}>
                    Clear filters
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <div
              style={{ height: virtualizer.getTotalSize(), position: 'relative' }}
              aria-live="polite"
              aria-relevant="additions"
            >
              {virtualizer.getVirtualItems().map((virtualRow) => {
                const event = filtered[virtualRow.index]
                if (!event) return null
                return (
                  <FeedRow
                    key={event.detail.seq}
                    event={event}
                    nameOf={nameOf}
                    role={employees[event.detail.employee_id ?? '']?.role}
                    flash={rate < FLASH_SUPPRESS_RATE && virtualRow.index < 3}
                    expanded={expanded === event.detail.task_id}
                    onToggle={() => {
                      const next = expanded === event.detail.task_id ? null : event.detail.task_id
                      setExpanded(next)
                      navigate(next ? `/live/${next}` : '/live')
                    }}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      height: virtualRow.size,
                      transform: `translateY(${virtualRow.start}px)`,
                    }}
                  />
                )
              })}
            </div>
          )}
        </div>
      </div>

      {expanded && <TracePanel taskId={expanded} onClose={() => setExpanded(null)} />}
    </div>
  )
}

function FeedRow({
  event,
  nameOf,
  role,
  flash,
  expanded,
  onToggle,
  style,
}: {
  event: EventEnvelope
  nameOf: (id: string) => string
  role?: string
  flash: boolean
  expanded: boolean
  onToggle: () => void
  style: React.CSSProperties
}) {
  const described = describeEvent(event, nameOf)

  return (
    <div
      style={style}
      onClick={onToggle}
      className={cn(
        'flex cursor-pointer items-center border-b border-line/60 transition-colors duration-75',
        'hover:bg-ink-700/60',
        expanded && 'bg-ink-600 border-l-2 border-l-shield',
        flash && 'animate-[rowflash_120ms_ease-out]',
      )}
    >
      <span className={cn(table.cellDense, 'w-14 text-text-faint')}>{described.time}</span>
      <span className={cn(table.cellDense, 'w-36 truncate')}>
        <span className="font-ui text-[12px] text-text">{described.who ?? '—'}</span>
        {role && (
          <span className="ml-1 font-ui text-[10px] text-text-faint">{roleLabel(role)}</span>
        )}
      </span>
      <span className={cn(table.cellDense, 'w-20 text-text-dim')}>
        {described.gate ?? '—'}
      </span>
      <span className={cn(table.cellDense, 'w-28 truncate text-text-dim')}>
        {described.what}
      </span>
      <span className={cn(table.cellDense, 'flex-1 truncate text-text-dim')}>
        {described.resource}
      </span>
      <span className={cn(table.cellDense, 'w-24')}>
        {described.decision && <DecisionChip decision={described.decision as Decision} />}
      </span>
      <span className={cn(table.cellDense, 'w-20 text-right text-spend')}>
        {described.cost ? formatMoney(described.cost) : '—'}
      </span>
    </div>
  )
}

/** The inline trace. One `GET /tasks/{id}` -- a single docstore query (A9). */
function TracePanel({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const navigate = useNavigate()
  const [trace, setTrace] = useState<Awaited<ReturnType<typeof endpoints.task>> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setTrace(null)
    endpoints
      .task(taskId)
      .then((data) => !cancelled && setTrace(data))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [taskId])

  const task = trace?.task as Record<string, unknown> | undefined

  return (
    <Panel>
      <div className="flex items-center justify-between border-b border-line px-4 py-2">
        <h3 className="font-mono text-[12px] text-text">
          {taskId}
          {task ? ` · ${String(task.title ?? '')}` : ''}
        </h3>
        <button onClick={onClose} className="text-text-faint hover:text-text" aria-label="Close">
          ✕
        </button>
      </div>

      <div className="p-4">
        {error && <p className="font-ui text-[12px] text-block">{error}</p>}
        {!trace && !error && <Skeleton className="h-24 w-full" />}

        {trace && (
          <>
            <h4 className="font-ui text-[11px] font-medium text-text-faint">TIMELINE</h4>
            <ol className="mt-2 space-y-1">
              {trace.gate1 && (
                <TraceRow
                  time={formatClock(Number(trace.gate1.sim_ts ?? 0))}
                  kind="gate1.decision"
                  decision={String(trace.gate1.decision ?? '')}
                  detail={`est ${formatMoney(Number(trace.gate1.est_cost_usd ?? 0))} · ${String(
                    trace.gate1.routed_model ?? '',
                  )}`}
                  policies={trace.gate1.matched_policies as { policy_id: string }[]}
                />
              )}
              {trace.actions.map((action) => (
                <TraceRow
                  key={String(action.id)}
                  time={formatClock(Number(action.sim_ts ?? 0))}
                  kind="gate2.decision"
                  decision={String(action.decision ?? '')}
                  detail={`${String(action.tool ?? '')} ${String(action.target_resource ?? '')}`}
                  policies={action.matched_policies as { policy_id: string }[]}
                />
              ))}
            </ol>

            <div className="mt-4 flex gap-2 border-t border-line pt-3">
              <Button
                variant="ghost"
                onClick={() => navigate(`/office?employee=${String(task?.employee_id ?? '')}`)}
              >
                View employee
              </Button>
              <Button variant="ghost" onClick={() => navigator.clipboard?.writeText(taskId)}>
                Copy task id
              </Button>
            </div>
          </>
        )}
      </div>
    </Panel>
  )
}

function TraceRow({
  time,
  kind,
  decision,
  detail,
  policies,
}: {
  time: string
  kind: string
  decision: string
  detail: string
  policies?: { policy_id: string }[]
}) {
  return (
    <li className="font-mono text-[12px] leading-5">
      <div className="flex items-center gap-2">
        <span className="text-text-faint">● {time}</span>
        <span className="w-32 text-text-dim">{kind}</span>
        {decision && <DecisionChip decision={decision as Decision} />}
        <span className="truncate text-text-dim">{detail}</span>
      </div>
      {policies && policies.length > 0 && (
        <div className="pl-[4.5rem] text-[11px] text-text-faint">
          matched: {policies.map((p) => p.policy_id).join(', ')}
        </div>
      )}
    </li>
  )
}

// ──────────────────────────────────────────────────────────────────────

function matches(
  event: EventEnvelope,
  filters: Filters,
  employees: Record<string, { team: string }>,
): boolean {
  const payload = event.detail.payload as Record<string, unknown>

  if (filters.employee && event.detail.employee_id !== filters.employee) return false

  if (filters.team) {
    const team = employees[event.detail.employee_id ?? '']?.team
    if (team !== filters.team) return false
  }

  if (filters.gate !== 'all') {
    const isGate1 = event.detail_type === 'gate1.decision'
    const isGate2 = event.detail_type === 'gate2.decision'
    if (filters.gate === '1' && !isGate1) return false
    if (filters.gate === '2' && !isGate2) return false
    if (filters.gate === 'none' && (isGate1 || isGate2)) return false
  }

  if (filters.decision && payload.decision !== filters.decision) return false
  if (filters.tool && payload.tool !== filters.tool) return false

  if (filters.search) {
    const haystack = JSON.stringify(payload).toLowerCase()
    if (!haystack.includes(filters.search.toLowerCase())) return false
  }

  return true
}

/** Rolling events-per-second, so the flash suppresses on evidence. */
function useEventRate(events: EventEnvelope[]): number {
  const [rate, setRate] = useState(0)
  const previous = useRef(events.length)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRate(Math.max(0, events.length - previous.current))
      previous.current = events.length
    }, 1000)
    return () => window.clearInterval(timer)
  }, [events.length])

  return rate
}
