import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AutopilotRoute from './autopilot'

const fixtures = [
  { fixture_id: 'buggy-auth', name: 'Session expiry', description: 'Repair session expiry.', suggested_goal: 'Fix auth' },
  { fixture_id: 'prompt-injection', name: 'Prompt injection', description: 'Untrusted README.', suggested_goal: 'Fix greeting' },
  { fixture_id: 'regression-guard', name: 'Regression guard', description: 'Repair shipping.', suggested_goal: 'Fix shipping' },
]

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('Autopilot evidence dashboard', () => {
  it('shows actionable missing-key setup and keeps fixture discovery available', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
      ok: !url.endsWith('/configuration'),
      json: async () => url.endsWith('/configuration')
        ? { detail: 'NEBIUS_API_KEY is not configured. Set NEBIUS_API_KEY in services/api/.env or export it.' }
        : { data: fixtures },
    })))
    render(<AutopilotRoute />)
    fireEvent.click(screen.getByText('Load fixtures'))
    expect(await screen.findByText('Autopilot setup required')).toBeInTheDocument()
    expect(screen.getByText('Repair session expiry.')).toBeInTheDocument()
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByText('Start coding job')).toBeDisabled()
  })

  it('renders completed mock evidence and downloads the actual report response', async () => {
    const receipt = { passed: true, exit_code: 0, stdout: '1 passed', stderr: '', duration_ms: 100, timed_out: false }
    const job = { id: 'mock-job', fixture_id: 'buggy-auth', goal: 'Fix auth', state: 'completed', verified: true,
      model_id: 'mock-for-ui-test', tokens_in: 100, tokens_out: 20, tool_calls: 3, repair_rounds: 1,
      baseline: { ...receipt, passed: false, exit_code: 1, stdout: '1 failed' }, after: receipt,
      diff: '@@ -1 +1 @@\n-broken\n+fixed', error: '' }
    const fetchMock = vi.fn(async (url: string) => ({ ok: true, json: async () => ({ data:
      url.endsWith('/configuration') ? { configured: true }
        : url.endsWith('/fixtures') ? fixtures
          : url.includes('/events') ? { events: [
            { detail_type: 'autopilot.gate', detail: { seq: 1, payload: { gate: 1, decision: 'allow' } } },
            { detail_type: 'autopilot.gate', detail: { seq: 2, payload: { gate: 2, decision: 'block' } } },
            { detail_type: 'autopilot.model', detail: { seq: 3, payload: { latency_ms: 1200 } } },
          ].filter(() => !url.includes('since_seq=3')), next_seq: 3 } : job,
    }) }))
    vi.stubGlobal('fetch', fetchMock)
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:mock') })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<AutopilotRoute />)
    fireEvent.click(screen.getByText('Load fixtures'))
    await waitFor(() => expect(screen.getByText('Start coding job')).toBeEnabled())
    fireEvent.click(screen.getByText('Start coding job'))
    expect(await screen.findByText('Before tests: FAIL · exit 1')).toBeInTheDocument()
    expect(screen.getByText('After tests: PASS · exit 0')).toBeInTheDocument()
    expect(await screen.findByText('Gate 2: block')).toBeInTheDocument()
    expect(screen.getByText('Gate 1: allow')).toBeInTheDocument()
    expect(screen.getByText('Model latency: 1.20 s total')).toBeInTheDocument()
    expect(screen.getByText('+fixed')).toHaveClass('text-green-300')
    expect(screen.getByText('-broken')).toHaveClass('text-red-300')
    fireEvent.click(screen.getByText('Download report'))
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/mock-job/report'), expect.any(Object))
  })
})
