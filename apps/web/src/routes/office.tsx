/**
 * The office route.
 *
 * Canvas on the left, system log on the right, employee drawer over the top.
 * The route owns the *layout*; the canvas owns nothing at all -- it is a
 * renderer over the telemetry stream, and if it and the Live Feed ever
 * disagree, the feed is right and the scene resnapshots.
 *
 * Three ways to end up on the card grid rather than Phaser, and only one of
 * them is an error: no WebGL, a failed snapshot, or the reader choosing
 * `Simple view`. The grid is a legitimate mode, not a fallback of last resort.
 */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { describeEvent } from '@/lib/format'
import { endpoints } from '@/lib/api'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'
import { useUi } from '@/stores/uiStore'
import { AvatarGrid } from '@/components/office/AvatarGrid'
import { EmployeeDrawer } from '@/components/employee/EmployeeDrawer'
import { Button, Dialog, Segmented } from '@/components/ui'
import { ReferenceOffice } from '@/game/ReferenceOffice'
import { DevelopmentFloor } from '@/game/DevelopmentFloor'

export default function OfficeRoute() {
  const [params, setParams] = useSearchParams()
  const selectedEmployee = params.get('employee')
  const [showLog, setShowLog] = useState(false)
  const floorPreview = import.meta.env.DEV && params.get('scene') === 'development'

  const simpleView = useUi((s) => s.simpleOfficeView)
  const toggleSimple = useUi((s) => s.toggleSimpleView)

  // Keep the employee drawer aligned with the optional system-log rail.
  const setSystemLogRail = useUi((s) => s.setSystemLogRail)
  useEffect(() => {
    setSystemLogRail(showLog)
    return () => setSystemLogRail(false)
  }, [setSystemLogRail, showLog])

  const select = (employeeId: string | null) => {
    const next = new URLSearchParams(params)
    if (employeeId) next.set('employee', employeeId)
    else next.delete('employee')
    setParams(next)
  }

  return (
    <div className="flex h-full">
      <div className="relative min-w-0 flex-1 bg-ink-950">
        <div className="office-action-dock absolute right-4 top-20 z-20 flex gap-2">
          <button
            className="rounded border border-line bg-ink-800 px-3 py-1 text-xs text-text"
            onClick={() => toggleSimple()}
          >
            {simpleView ? 'Office view' : 'Simple view'}
          </button>
          <button
            className="rounded border border-line bg-ink-800 px-3 py-1 text-xs text-text"
            aria-pressed={showLog}
            onClick={() => setShowLog(!showLog)}
          >
            {showLog ? 'Hide system log' : 'System log'}
          </button>
          {import.meta.env.DEV && (
            <button
              className="rounded border border-line bg-ink-800 px-3 py-1 text-xs text-text"
              onClick={() => {
                const next = new URLSearchParams(params)
                if (floorPreview) next.delete('scene')
                else next.set('scene', 'development')
                setParams(next)
              }}
            >
              {floorPreview ? '5-Room Office' : 'Dev Floor Study'}
            </button>
          )}
        </div>
        {!simpleView ? (
          floorPreview ? (
            <DevelopmentFloor onSelect={select} selectedId={selectedEmployee} />
          ) : (
            <ReferenceOffice onSelect={select} selectedId={selectedEmployee} />
          )
        ) : (
          <div className="relative h-full overflow-y-auto">
            <AvatarGrid onSelect={select} />
            <div className="sticky bottom-4 mr-4 flex justify-end">
              <button
                onClick={() => toggleSimple()}
                className="flex h-7.5 items-center gap-2 rounded-sm border border-line bg-ink-800 px-3 text-xs text-text-dim shadow-panel transition-colors hover:border-line-strong hover:text-text"
              >
                <svg
                  width="13"
                  height="13"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                </svg>
                Office view
              </button>
            </div>
          </div>
        )}
      </div>

      {showLog && <SystemLog />}

      <EmployeeDrawer employeeId={selectedEmployee} onClose={() => select(null)} />
    </div>
  )
}

/**
 * The system log rail.
 *
 * Rendered from the same `telemetryStore` events the Live Feed uses, formatted
 * by `describeEvent`. Auto-scrolls unless the reader has scrolled up, in which
 * case a pill appears rather than yanking them back to the top.
 */
function SystemLog() {
  const log = useTelemetry((s) => s.log)
  const nameOf = useSim((s) => s.nameOf)

  const ref = useRef<HTMLDivElement>(null)
  const [stuck, setStuck] = useState(true)
  const [unseen, setUnseen] = useState(0)

  useEffect(() => {
    if (!ref.current) return
    if (stuck) {
      ref.current.scrollTop = 0
      setUnseen(0)
    } else {
      setUnseen((n) => n + 1)
    }
  }, [log.length, stuck])

  const reversed = [...log].reverse()

  return (
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-line bg-[#0D1522] shadow-[-8px_0_32px_#00000030]">
      <header className="flex h-10 shrink-0 items-center justify-center relative border-b border-line px-3">
        <h2 className="font-ui text-[11px] font-semibold tracking-[0.12em] text-text-dim text-center">
          SYSTEM LOG
        </h2>
        {!stuck && unseen > 0 && (
          <button
            onClick={() => {
              setStuck(true)
              if (ref.current) ref.current.scrollTop = 0
            }}
            className="absolute right-3 rounded-xs bg-shield-subtle px-1.5 py-0.5 font-mono text-[10px] text-shield"
          >
            ↓ {unseen} new
          </button>
        )}
      </header>

      <div
        ref={ref}
        onScroll={(e) => setStuck(e.currentTarget.scrollTop < 8)}
        className="flex-1 overflow-y-auto"
        aria-live="polite"
        aria-relevant="additions"
      >
        {log.length === 0 && (
          <div className="p-4 font-mono text-[11px] text-text-faint text-center space-y-2">
            <p>Waiting for the first request.</p>
            <p className="text-[10px] text-text-faint/80">Press ▶ Real time to start.</p>
          </div>
        )}

        {reversed.map((event) => {
          const described = describeEvent(event, nameOf)
          return (
            <div
              key={event.detail.seq}
              className="cursor-pointer px-3 py-1 font-mono text-[11px] leading-[18px] hover:bg-ink-700/50"
            >
              <span className="text-text-faint">[{described.time}]</span>{' '}
              <span className="text-text-dim">{described.text}</span>
              {described.decision && (
                <span
                  className={cn(
                    'ml-1 font-medium',
                    described.decision === 'allow' && 'text-allow',
                    described.decision === 'redact' && 'text-redact',
                    described.decision === 'review' && 'text-review',
                    described.decision === 'block' && 'text-block',
                  )}
                >
                  {described.decision === 'block' ? '- Blocked by AGENTSHIELD Gate 2' : described.decision.toUpperCase()}
                </span>
              )}
            </div>
          )
        })}
      </div>
    </aside>

  )
}

/**
 * The fast-forward dialog.
 *
 * 100x replaces the canvas rather than speeding it up. Rendering a week as
 * motion would be an unreadable strobe and would drop frames; a progress meter
 * and a summary card are both more honest and more useful.
 */
export function FastForwardDialog({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const run = useSim((s) => s.run)
  const progress = useSim((s) => s.progress)
  const setProgress = useSim((s) => s.setProgress)
  const refreshSnapshot = useSim((s) => s.refreshSnapshot)
  const setLastSeq = useTelemetry((s) => s.setLastSeq)
  const clearQueue = useTelemetry((s) => s.clearOfficeQueue)
  const toast = useUi((s) => s.toast)

  const [days, setDays] = useState(7)
  const [running, setRunning] = useState(false)
  const [summary, setSummary] = useState<Record<string, number> | null>(null)

  const start = async () => {
    if (!run) return
    setRunning(true)
    setSummary(null)
    try {
      const result = await endpoints.advance(run.id, { sim_days: days })
      setSummary(result)
    } catch (e) {
      toast('error', `The fast-forward stopped: ${(e as Error).message}`)
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  const back = async () => {
    if (run) {
      // Hard cut. The office reappears at the new sim time rather than
      // animating through everything it missed.
      const seq = await refreshSnapshot(run.id)
      setLastSeq(seq)
      clearQueue()
    }
    setSummary(null)
    onClose()
  }

  return (
    <Dialog open={open} onClose={onClose} title="Fast-forward the simulation">
      {!running && !summary && (
        <>
          <span className="block font-ui text-[11px] font-medium text-text-faint">
            How far?
          </span>
          <div className="mt-2">
            <Segmented
              value={days}
              onChange={setDays}
              options={[
                { value: 1, label: '1 day' },
                { value: 7, label: '1 week' },
                { value: 30, label: '30 days' },
              ]}
            />
          </div>
          <p className="mt-3 font-ui text-[12px] text-text-dim">
            Avatars pause while this runs. The office resyncs when it finishes.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void start()}>
              Run
            </Button>
          </div>
        </>
      )}

      {running && (
        <div className="py-4 text-center">
          <p className="font-pixel text-[13px] tracking-[0.02em] text-text">
            SIMULATING {days} {days === 1 ? 'DAY' : 'DAYS'}
          </p>
          <div className="mx-auto mt-3 h-2 w-64 overflow-hidden rounded-xs bg-ink-700">
            <div
              className="h-full bg-shield transition-[width] duration-300"
              style={{
                width: `${Math.min(100, ((progress?.sim_day ?? 0) / days) * 100)}%`,
              }}
            />
          </div>
          <p className="mt-2 font-mono text-[12px] tabular-nums text-text-dim">
            day {progress?.sim_day ?? 0} of {days}
          </p>
          <p className="font-mono text-[12px] tabular-nums text-text-faint">
            {(progress?.events_generated ?? 0).toLocaleString()} events generated
          </p>
        </div>
      )}

      {summary && (
        <div className="py-2">
          <p className="text-center font-pixel text-[13px] tracking-[0.02em] text-text">
            SIMULATION COMPLETE
          </p>
          <dl className="mx-auto mt-4 w-56 space-y-1 border-y border-line py-3">
            <SummaryRow label="agent requests" value={summary.tasks ?? 0} />
            <SummaryRow label="events" value={summary.events_generated ?? 0} />
            <SummaryRow label="blocked actions" value={summary.blocked ?? 0} />
            <SummaryRow label="approvals" value={summary.approvals ?? 0} />
            <SummaryRow
              label="simulated spend"
              value={`$${(summary.cost_usd ?? 0).toFixed(2)}`}
            />
          </dl>
          <div className="mt-4 flex justify-center gap-2">
            <Button variant="secondary" onClick={back}>
              Back to the office
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}

function SummaryRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-baseline justify-between">
      <dt className="font-ui text-[11px] text-text-faint">{label}</dt>
      <dd className="font-mono text-[13px] tabular-nums text-text">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </dd>
    </div>
  )
}
