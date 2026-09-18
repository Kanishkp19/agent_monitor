/**
 * The persistent chrome: header, nav, run pill, sim clock, speed, role.
 *
 * Two body modes, from `docs/03-APP-FLOW.md` section 3:
 * - `full-bleed` for the office, where the canvas owns the space
 * - `padded` for everything else
 *
 * The header is where the simulation is controlled from, which is why the
 * speed control and the connection dot live here rather than on the office
 * route -- they apply to every screen, and a reader on the Live Feed still
 * needs to know the socket dropped.
 */

import { useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Activity, Bell, Building2, ListFilter, ShieldCheck, SlidersHorizontal } from 'lucide-react'

import { cn } from '@/lib/cn'
import { formatSimTime } from '@/lib/format'
import { endpoints } from '@/lib/api'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'
import { useUi, type ViewAs } from '@/stores/uiStore'
import { Segmented } from '@/components/ui'

const NAV = [
  { to: '/office', label: 'OFFICE', icon: Building2 },
  { to: '/live', label: 'LIVE FEED', icon: ListFilter },
  { to: '/approvals', label: 'APPROVALS', icon: Bell },
  { to: '/control', label: 'CONTROL CENTER', icon: SlidersHorizontal },
]

const ROLES: { value: ViewAs; label: string }[] = [
  { value: 'security_admin', label: 'Security' },
  { value: 'manager', label: 'Manager' },
  { value: 'ceo', label: 'CEO' },
  { value: 'engineer', label: 'Engineer' },
]

export function AppShell({
  children,
  mode = 'padded',
  onFastForward,
}: {
  children: React.ReactNode
  mode?: 'padded' | 'full-bleed'
  onFastForward?: () => void
}) {
  return (
    <div className="flex h-full flex-col bg-ink-900">
      <Header onFastForward={onFastForward} />
      <main
        className={cn(
          'flex-1 min-h-0',
          mode === 'padded' ? 'overflow-y-auto' : 'overflow-hidden',
        )}
      >
        {mode === 'padded' ? (
          <div className="mx-auto max-w-[1600px] px-6 py-5">{children}</div>
        ) : (
          children
        )}
      </main>
      <WidthNotice />
    </div>
  )
}

function Header({ onFastForward }: { onFastForward?: () => void }) {
  const { pathname } = useLocation()
  const run = useSim((s) => s.run)
  const simTs = useSim((s) => s.simTs)
  const speed = useSim((s) => s.speed)
  const pending = useSim((s) => s.pendingApprovals)
  const connected = useTelemetry((s) => s.connected)

  return (
    <header className="flex h-14 shrink-0 items-center gap-1 border-b border-line bg-ink-900 px-4">
      <NavLink to="/office" className="mr-2 flex items-center gap-2" aria-label="AgentShield">
        <ShieldCheck className="h-5 w-5 text-shield" strokeWidth={2} />
      </NavLink>

      <nav className="flex items-center">
        {NAV.map(({ to, label, icon: Icon }) => {
          const active = pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              className={cn(
                'relative inline-flex h-14 items-center gap-1.5 px-3 font-ui text-[13px]',
                'transition-colors duration-100',
                active
                  ? 'font-medium text-text after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-shield'
                  : 'text-text-dim hover:text-text',
              )}
            >
              <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
              {label}
            </NavLink>
          )
        })}
      </nav>

      <div className="flex-1" />

      <div className="flex items-center gap-3">
        <RunPill />
        <SimClock simTs={simTs} speed={speed} />
        <SpeedControl onFastForward={onFastForward} />
        <ConnectionDot connected={connected} />
        <ApprovalsBadge count={pending} />
        <RoleSelector />
      </div>

      {!run && <span className="sr-only">No run loaded</span>}
    </header>
  )
}

function RunPill() {
  const run = useSim((s) => s.run)
  if (!run) {
    return (
      <span className="font-mono text-[11px] tabular-nums text-text-faint">no run</span>
    )
  }
  return (
    <span className="rounded-xs border border-line bg-ink-800 px-2 py-1 font-mono text-[11px] tabular-nums text-text-dim">
      {run.id} · day {run.sim_day}
    </span>
  )
}

/**
 * The sim clock, in Departure Mono.
 *
 * This is one of only two places the pixel face appears in the console -- it
 * is the product admitting, quietly, that you are looking at a simulation.
 */
function SimClock({ simTs, speed }: { simTs: number; speed: number }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="font-pixel text-[13px] leading-4 tracking-[0.02em] text-text">
        {formatSimTime(simTs)}
      </span>
      {speed !== 1 && (
        <span className="font-mono text-[10px] tabular-nums text-text-faint">×{speed}</span>
      )}
    </span>
  )
}

function SpeedControl({ onFastForward }: { onFastForward?: () => void }) {
  const run = useSim((s) => s.run)
  const speed = useSim((s) => s.speed)
  const setSpeed = useSim((s) => s.setSpeed)
  const toast = useUi((s) => s.toast)

  const change = async (next: number) => {
    if (!run) return

    // 100x does not switch immediately -- it opens the fast-forward dialog,
    // because it replaces the canvas rather than speeding it up.
    if (next === 100) {
      onFastForward?.()
      return
    }

    setSpeed(next)
    try {
      if (next === 0) {
        await endpoints.control(run.id, { action: 'pause' })
      } else {
        await endpoints.control(run.id, { action: 'set_speed', speed: next })
      }
    } catch (error) {
      toast('error', (error as Error).message)
    }
  }

  return (
    <Segmented
      value={speed}
      onChange={change}
      options={[
        { value: 1, label: '▶ REAL TIME' },
        { value: 10, label: '▶▶ 10×' },
        { value: 100, label: '▶▶▶ 100×' },
        { value: 0, label: '⏸' },
      ]}
    />
  )
}

function ConnectionDot({ connected }: { connected: boolean }) {
  return (
    <span
      className="flex items-center gap-1.5"
      title={connected ? 'Connected' : 'Reconnecting…'}
    >
      <span
        className={cn('h-1.5 w-1.5 rounded-full', connected ? 'bg-allow' : 'bg-review')}
      />
      <span className="sr-only">{connected ? 'Connected' : 'Reconnecting'}</span>
    </span>
  )
}

function ApprovalsBadge({ count }: { count: number }) {
  return (
    <NavLink
      to="/approvals"
      className="relative inline-flex h-8 w-8 items-center justify-center rounded-sm text-text-dim hover:bg-ink-700 hover:text-text"
      aria-label={`${count} pending approvals`}
    >
      <Bell className="h-4 w-4" strokeWidth={1.75} />
      {count > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-review px-1 font-mono text-[9px] font-semibold tabular-nums text-ink-950 animate-[badgepulse_240ms_ease-out]">
          {count}
        </span>
      )}
    </NavLink>
  )
}

function RoleSelector() {
  const viewAs = useUi((s) => s.viewAs)
  const setViewAs = useUi((s) => s.setViewAs)

  return (
    <select
      value={viewAs}
      onChange={(e) => setViewAs(e.target.value as ViewAs)}
      aria-label="View as role"
      className="h-8 appearance-none rounded-sm border border-line bg-ink-900 pl-2.5 pr-6 font-ui text-[12px] text-text focus:border-shield focus:outline-none"
    >
      {ROLES.map((role) => (
        <option key={role.value} value={role.value}>
          {role.label}
        </option>
      ))}
    </select>
  )
}

/**
 * Below 1024px, say so.
 *
 * A half-working console is worse than an honest notice. This is a deliberate
 * scope decision, not an omission -- an ops console at 375px is a different
 * product.
 */
function WidthNotice() {
  useEffect(() => {
    const onResize = () => {
      document.documentElement.dataset.narrow = String(window.innerWidth < 1024)
    }
    onResize()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  return (
    <div className="fixed inset-0 z-[100] hidden flex-col items-center justify-center gap-2 bg-ink-900 [html[data-narrow='true']_&]:flex">
      <Activity className="h-6 w-6 text-text-faint" strokeWidth={1.5} />
      <p className="font-ui text-[13px] font-medium text-text">
        AgentShield needs a wider window.
      </p>
      <p className="font-ui text-[12px] text-text-faint">Minimum 1024px.</p>
    </div>
  )
}
