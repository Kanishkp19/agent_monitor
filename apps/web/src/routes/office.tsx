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

import { Suspense, lazy, useEffect, useRef, useState } from 'react'
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

// Phaser is ~1.2MB. Loading it lazily keeps the console's first paint off the
// critical path of a game engine, and means a reader who never opens the
// office never downloads one.
const PhaserGame = lazy(() =>
  import('@/game/PhaserGame').then((m) => ({ default: m.PhaserGame })),
)

export default function OfficeRoute() {
  const [params, setParams] = useSearchParams()
  const selectedEmployee = params.get('employee')

  const simpleView = useUi((s) => s.simpleOfficeView)
  const toggleSimple = useUi((s) => s.toggleSimpleView)

  const [webglFailed, setWebglFailed] = useState(!hasWebGL())
  const useCanvas = !simpleView && !webglFailed

  const select = (employeeId: string | null) => {
    const next = new URLSearchParams(params)
    if (employeeId) next.set('employee', employeeId)
    else next.delete('employee')
    setParams(next)
  }

  return (
    <div className="flex h-full">
      <div className="relative min-w-0 flex-1 bg-ink-950">
        {useCanvas ? (
          <Suspense fallback={<CanvasLoading />}>
            <PhaserGame onSelect={select} onError={() => setWebglFailed(true)} />
          </Suspense>
        ) : (
          <div className="h-full overflow-y-auto">
            {webglFailed && !simpleView && (
              <div className="flex items-center gap-3 border-b border-line bg-ink-800 px-4 py-2">
                <p className="flex-1 font-ui text-[12px] text-text-dim">
                  Couldn&apos;t load the floor. Showing a simple view.
                </p>
                <Button variant="ghost" onClick={() => setWebglFailed(false)}>
                  Retry
                </Button>
              </div>
            )}
            <AvatarGrid onSelect={select} />
          </div>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between p-3">
          <div className="pointer-events-auto">
            <Segmented
              value={simpleView ? 'grid' : 'canvas'}
              onChange={() => toggleSimple()}
              options={[
                { value: 'canvas', label: 'Office' },
                { value: 'grid', label: 'Simple view' },
              ]}
            />
          </div>
          <Legend />
        </div>
      </div>

      <SystemLog />

      <EmployeeDrawer employeeId={selectedEmployee} onClose={() => select(null)} />
    </div>
  )
}

function CanvasLoading() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 bg-ink-950">
      <p className="font-pixel text-[13px] tracking-[0.02em] text-text-dim">
        Loading the floor…
      </p>
    </div>
  )
}

function Legend() {
  const items = [
    { label: 'working', color: 'bg-allow' },
    { label: 'waiting', color: 'bg-review' },
    { label: 'blocked', color: 'bg-block' },
    { label: 'idle', color: 'bg-idle' },
  ]
  return (
    <div className="flex items-center gap-3 rounded-sm border border-line bg-ink-800/80 px-3 py-1.5 backdrop-blur-sm">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5">
          <span className={cn('h-1.5 w-1.5 rounded-full', item.color)} />
          <span className="font-ui text-[11px] text-text-dim">{item.label}</span>
        </span>
      ))}
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
    <aside className="flex w-[340px] shrink-0 flex-col border-l border-line bg-ink-900">
      <header className="flex h-10 shrink-0 items-center justify-between border-b border-line px-3">
        <h2 className="font-ui text-[11px] font-medium text-text-faint">SYSTEM LOG</h2>
        {!stuck && unseen > 0 && (
          <button
            onClick={() => {
              setStuck(true)
              if (ref.current) ref.current.scrollTop = 0
            }}
            className="rounded-xs bg-shield-subtle px-1.5 py-0.5 font-mono text-[10px] text-shield"
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
          <p className="p-3 font-ui text-[12px] text-text-faint">
            Waiting for the first request. Press ▶ to start.
          </p>
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
                  {described.decision.toUpperCase()}
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

/**
 * Probe for WebGL before Phaser tries.
 *
 * Phaser falls back to Canvas on its own, but a machine with no WebGL at all
 * is also a machine where the card grid is the better experience -- and
 * finding out by catching an init failure means a blank frame first.
 */
function hasWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(
      canvas.getContext('webgl2') ??
        canvas.getContext('webgl') ??
        canvas.getContext('experimental-webgl'),
    )
  } catch {
    return false
  }
}
