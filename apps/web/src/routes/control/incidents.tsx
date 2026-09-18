/**
 * The incident list.
 *
 * An incident is what the detector concluded, with the evidence that led there.
 * The empty state reads "No incidents. That's the goal." -- deliberately
 * quieter in tone than an error, because an empty list here is good news.
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { endpoints, type Incident } from '@/lib/api'
import { formatClock, roleLabel } from '@/lib/format'
import { riskColor } from '@/lib/risk'
import { useSim } from '@/stores/simStore'
import { useUi } from '@/stores/uiStore'
import {
  Button,
  Chip,
  EmptyState,
  ErrorState,
  Panel,
  Segmented,
  Skeleton,
} from '@/components/ui'

export default function IncidentsRoute() {
  const navigate = useNavigate()
  const run = useSim((s) => s.run)
  const nameOf = useSim((s) => s.nameOf)
  const employees = useSim((s) => s.employees)
  const toast = useUi((s) => s.toast)

  const [status, setStatus] = useState<'open' | 'acknowledged' | 'closed'>('open')
  const [incidents, setIncidents] = useState<Incident[] | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!run) return
    try {
      setError(null)
      setIncidents(await endpoints.incidents(run.id, status))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [run, status])

  useEffect(() => {
    void load()
  }, [load])

  const acknowledge = async (incident: Incident) => {
    if (!run) return
    try {
      await endpoints.acknowledgeIncident(run.id, incident.id)
      toast('success', 'Acknowledged.')
      void load()
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  if (error) {
    return <ErrorState title="Couldn't load incidents." detail={error} onRetry={load} />
  }

  return (
    <div className="flex flex-col gap-4">
      <Segmented
        value={status}
        onChange={setStatus}
        options={[
          { value: 'open', label: 'Open' },
          { value: 'acknowledged', label: 'Acknowledged' },
          { value: 'closed', label: 'Closed' },
        ]}
      />

      {incidents === null && (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full rounded-md" />
          ))}
        </div>
      )}

      {incidents?.length === 0 && (
        <Panel>
          <EmptyState
            title="No incidents. That's the goal."
            hint={
              status === 'open'
                ? 'An incident opens when risk crosses 70 for two consecutive sessions, or on any single critical event.'
                : undefined
            }
          />
        </Panel>
      )}

      {incidents?.map((incident) => {
        const isOpen = expanded === incident.id
        const employee = employees[incident.employee_id]

        return (
          <Panel key={incident.id}>
            <div
              onClick={() => setExpanded(isOpen ? null : incident.id)}
              className="flex cursor-pointer items-center gap-3 px-4 py-3"
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ background: riskColor(incident.score) }}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <p className="font-ui text-[13px] font-medium text-text">
                  {nameOf(incident.employee_id)}
                  {employee && (
                    <span className="ml-2 font-ui text-[11px] font-normal text-text-faint">
                      {roleLabel(employee.role)} · {employee.team}
                    </span>
                  )}
                </p>
                <p className="truncate font-ui text-[12px] text-text-dim">
                  {incident.summary}
                </p>
              </div>
              <Chip>{incident.detector.replace(/_/g, ' ')}</Chip>
              <span className="font-mono text-[12px] tabular-nums text-text">
                {incident.score}
              </span>
              <span className="font-mono text-[11px] tabular-nums text-text-faint">
                {formatClock(incident.opened_sim_ts)}
              </span>
            </div>

            {isOpen && (
              <div className="border-t border-line p-4">
                <h4 className="font-ui text-[11px] font-medium text-text-faint">
                  EVIDENCE TRAIL
                </h4>
                <ul className="mt-2 space-y-0.5">
                  {incident.evidence.map((item) => (
                    <li
                      key={item.event_seq}
                      onClick={() => navigate(`/live?seq=${item.event_seq}`)}
                      className={cn(
                        'flex cursor-pointer items-center gap-3 rounded-xs px-1 py-0.5',
                        'font-mono text-[12px] hover:bg-ink-700/60',
                      )}
                    >
                      <span className="tabular-nums text-text-faint">
                        {formatClock(item.sim_ts)}
                      </span>
                      <span className="w-32 truncate text-text-dim">{item.kind}</span>
                      <span className="flex-1 truncate text-text-dim">{item.detail}</span>
                    </li>
                  ))}
                  {incident.evidence.length === 0 && (
                    <li className="font-ui text-[12px] text-text-faint">
                      No individual events recorded — this incident opened on a composite score.
                    </li>
                  )}
                </ul>

                <div className="mt-4 flex gap-2 border-t border-line pt-3">
                  {incident.status === 'open' && (
                    <Button variant="secondary" onClick={() => void acknowledge(incident)}>
                      Acknowledge
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    onClick={() => navigate(`/office?employee=${incident.employee_id}`)}
                  >
                    View employee
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      navigate(`/control/risk?employee=${incident.employee_id}`)
                    }
                  >
                    View risk explanation
                  </Button>
                </div>
              </div>
            )}
          </Panel>
        )
      })}
    </div>
  )
}
