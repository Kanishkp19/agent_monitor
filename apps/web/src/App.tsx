/**
 * Routes, and the one place the WebSocket is wired to the stores.
 *
 * The connection lives here rather than in a route because it must survive
 * navigation -- a reader moving from the office to the Live Feed should not
 * drop and replay the stream.
 */

import { useEffect, useState } from 'react'
import {
  BrowserRouter,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { cn } from '@/lib/cn'
import { connectStream } from '@/lib/ws'
import { AppShell } from '@/components/layout/AppShell'
import { Toaster } from '@/components/layout/Toaster'
import { EmployeeDrawer } from '@/components/employee/EmployeeDrawer'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'
import { useUi } from '@/stores/uiStore'
import { Button, EmptyState } from '@/components/ui'

import OfficeRoute, { FastForwardDialog } from '@/routes/office'
import LiveFeedRoute from '@/routes/live'
import ApprovalsRoute from '@/routes/approvals'
import ControlOverviewRoute from '@/routes/control/index'
import SandboxRoute from '@/routes/sandbox'
import PoliciesRoute from '@/routes/control/policies'
import PolicyLabRoute from '@/routes/control/policy-lab'
import EmployeesRoute from '@/routes/control/employees'
import CostsRoute from '@/routes/control/costs'
import RiskRoute from '@/routes/control/risk'
import IncidentsRoute from '@/routes/control/incidents'
import AutopilotRoute from '@/routes/autopilot'

import '@/styles/globals.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 2, refetchOnWindowFocus: false, staleTime: 5_000 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell />
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function Shell() {
  const { pathname } = useLocation()
  const run = useSim((s) => s.run)
  const loadLatestRun = useSim((s) => s.loadLatestRun)
  const error = useSim((s) => s.error)

  const [fastForwardOpen, setFastForwardOpen] = useFastForward()

  useEffect(() => {
    void loadLatestRun()
  }, [loadLatestRun])

  useStream(run?.id)

  const fullBleed = pathname.startsWith('/office')

  if (pathname.startsWith('/autopilot')) {
    return <AppShell><AutopilotRoute /></AppShell>
  }

  if (error) {
    return (
      <AppShell>
        <EmptyState
          title="Can't reach the AgentShield API."
          hint={import.meta.env.VITE_API_BASE ?? '/api/v1'}
          action={
            <Button variant="primary" onClick={() => void loadLatestRun()}>
              Retry
            </Button>
          }
        />
      </AppShell>
    )
  }

  if (!run) {
    return (
      <AppShell>
        <EmptyState
          title="No simulation yet."
          hint="Seed one with `python tasks.py seed`, then reload."
          action={
            <Button variant="primary" onClick={() => void loadLatestRun()}>
              Check again
            </Button>
          }
        />
      </AppShell>
    )
  }

  return (
    <AppShell
      mode={fullBleed ? 'full-bleed' : 'padded'}
      onFastForward={() => setFastForwardOpen(true)}
    >
      <Routes>
        <Route path="/" element={<Navigate to="/office" replace />} />
        <Route path="/office" element={<OfficeRoute />} />
        <Route path="/live" element={<LiveFeedRoute />} />
        <Route path="/live/:taskId" element={<LiveFeedRoute />} />
        <Route path="/approvals" element={<ApprovalsRoute />} />
        <Route path="/sandbox" element={<SandboxRoute />} />
        <Route path="/autopilot" element={<AutopilotRoute />} />

        <Route path="/control" element={<ControlLayout />}>
          <Route index element={<ControlOverviewRoute />} />
          <Route path="policies" element={<PoliciesRoute />} />
          <Route path="policy-lab" element={<PolicyLabRoute />} />
          <Route path="employees" element={<EmployeesRoute />} />
          <Route path="costs" element={<CostsRoute />} />
          <Route path="risk" element={<RiskRoute />} />
          <Route path="incidents" element={<IncidentsRoute />} />
        </Route>

        <Route
          path="*"
          element={
            <EmptyState
              title="That page doesn't exist."
              action={
                <NavLink to="/office">
                  <Button variant="secondary">Back to the office</Button>
                </NavLink>
              }
            />
          }
        />
      </Routes>

      <FastForwardDialog
        open={fastForwardOpen}
        onClose={() => setFastForwardOpen(false)}
      />
    </AppShell>
  )
}

const CONTROL_NAV = [
  { to: '/control', label: 'Overview', end: true },
  { to: '/control/policies', label: 'Policies' },
  { to: '/control/policy-lab', label: 'Policy Lab' },
  { to: '/control/employees', label: 'Employees' },
  { to: '/control/costs', label: 'Costs' },
  { to: '/control/risk', label: 'Risk' },
  { to: '/control/incidents', label: 'Incidents' },
]

/**
 * A horizontal tab strip, not a sidebar.
 *
 * The office needs the full width, and a second vertical rail would fight it.
 */
function ControlLayout() {
  const selectedEmployee = useUi((s) => s.selectedEmployee)
  const selectEmployee = useUi((s) => s.selectEmployee)

  return (
    <div className="flex flex-col gap-5">
      <nav className="flex h-10 items-center gap-1 border-b border-line">
        {CONTROL_NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'relative inline-flex h-10 items-center px-3 font-ui text-[13px]',
                'transition-colors duration-100',
                isActive
                  ? 'font-medium text-text after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-shield'
                  : 'text-text-dim hover:text-text',
              )
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />

      {/* The same drawer the office uses, so a row click and an avatar click
          land on identical content. */}
      <EmployeeDrawer
        employeeId={selectedEmployee}
        onClose={() => selectEmployee(null)}
      />
    </div>
  )
}

/**
 * One socket for the lifetime of the run.
 *
 * Resumes from `lastSeq` on reconnect; a gap over 500 events resnapshots
 * instead of replaying, because animating a catch-up would misrepresent when
 * things happened.
 */
function useStream(runId: string | undefined) {
  const ingest = useTelemetry((s) => s.ingest)
  const setConnected = useTelemetry((s) => s.setConnected)
  const setLastSeq = useTelemetry((s) => s.setLastSeq)
  const clearQueue = useTelemetry((s) => s.clearOfficeQueue)
  const applyEvent = useSim((s) => s.applyEvent)
  const refreshSnapshot = useSim((s) => s.refreshSnapshot)
  const setProgress = useSim((s) => s.setProgress)

  useEffect(() => {
    if (!runId) return

    return connectStream(runId, {
      lastSeq: () => useTelemetry.getState().lastSeq,
      onStatus: setConnected,
      onEvents: (events) => {
        ingest(events)
        for (const event of events) applyEvent(event)
      },
      onProgress: setProgress,
      onResnapshot: () => {
        void refreshSnapshot(runId).then((seq) => {
          setLastSeq(seq)
          clearQueue()
        })
      },
    })
  }, [
    runId,
    ingest,
    applyEvent,
    setConnected,
    setLastSeq,
    clearQueue,
    refreshSnapshot,
    setProgress,
  ])
}

function useFastForward(): [boolean, (open: boolean) => void] {
  const [open, setOpen] = useState(false)
  return [open, setOpen]
}
