import { useCallback, useEffect, useState } from 'react'
import { Check, Copy, Download, Loader2, LockKeyhole, Play, ShieldCheck, Sparkles, Terminal } from 'lucide-react'
import type { EventEnvelope } from '../types/generated'

type Fixture = { fixture_id: string; name: string; description: string; suggested_goal: string }
type TestReceipt = { passed: boolean; exit_code: number; stdout: string; stderr: string; duration_ms: number; timed_out: boolean }
type Job = {
  id: string; fixture_id: string; goal: string; state: string; verified: boolean
  model_id: string; tokens_in: number; tokens_out: number; tool_calls: number
  repair_rounds: number; baseline: TestReceipt | null; after: TestReceipt | null
  diff: string; error: string
}
type Event = Pick<EventEnvelope, 'detail_type' | 'detail'>

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'
const terminal = new Set(['completed', 'failed', 'blocked'])

async function call<T>(token: string, path: string, body?: object): Promise<T> {
  const response = await fetch(`${BASE}/autopilot${path}`, {
    method: body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body ? JSON.stringify(body) : undefined,
  })
  const payload = await response.json()
  if (!response.ok) throw new Error(payload.detail ?? payload.error?.message ?? response.statusText)
  return payload.data as T
}

function Receipt({ title, result }: { title: string; result: TestReceipt | null }) {
  return <section className="receipt console-panel">
    <div className="receipt-chrome"><span aria-hidden="true" className="terminal-dots">● ● ●</span><span>TEST RUNNER</span><Terminal size={14} aria-hidden="true" /></div>
    <div className="p-4">
      <h3 className={`font-mono text-xs ${!result ? 'text-text-dim' : result.passed ? 'text-allow' : 'text-block'}`}>{title}{result ? `: ${result.passed ? 'PASS' : 'FAIL'} · exit ${result.exit_code}` : ': waiting'}</h3>
      <p className="mt-1 text-xs text-text-dim">{result ? `${Math.round(result.duration_ms)} ms${result.timed_out ? ' · timed out' : ''}` : 'Receipt appears after the test runner finishes.'}</p>
    </div>
    <pre className="receipt-output">{result ? result.stdout + result.stderr || 'No output captured.' : '$ awaiting test output'}</pre>
  </section>
}

export default function AutopilotRoute() {
  const [token, setToken] = useState('demo-autopilot-2026')
  const [fixtures, setFixtures] = useState<Fixture[]>([])
  const [fixtureId, setFixtureId] = useState('')
  const [goal, setGoal] = useState('')
  const [job, setJob] = useState<Job | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [cursor, setCursor] = useState(0)
  const [error, setError] = useState('')
  const [configurationError, setConfigurationError] = useState('')
  const [configured, setConfigured] = useState(false)
  const [copied, setCopied] = useState(false)

  const loadFixtures = useCallback(async () => {
    setConfigured(false)
    setConfigurationError('')
    void call<{ configured: boolean }>(token, '/configuration')
      .then(() => setConfigured(true))
      .catch((err) => setConfigurationError(String(err)))
    try {
      const list = await call<Fixture[]>(token, '/fixtures')
      setFixtures(list)
      const first = list[0]
      if (first) { setFixtureId(first.fixture_id); setGoal(first.suggested_goal) }
      setError('')
    } catch (err) { setError(String(err)) }
  }, [token])

  useEffect(() => {
    if (!job || terminal.has(job.state)) return
    const timer = window.setInterval(() => {
      void call<Job>(token, `/jobs/${job.id}`).then(setJob).catch((err) => setError(String(err)))
      void call<{ events: Event[]; next_seq: number }>(token, `/jobs/${job.id}/events?since_seq=${cursor}`)
        .then((page) => { setEvents((current) => [...current, ...page.events]); setCursor(page.next_seq) })
        .catch((err) => setError(String(err)))
    }, 1500)
    return () => window.clearInterval(timer)
  }, [token, job, cursor])

  useEffect(() => {
    if (!job || !terminal.has(job.state)) return
    void call<{ events: Event[]; next_seq: number }>(
      token, `/jobs/${job.id}/events?since_seq=${cursor}`,
    ).then((page) => {
      if (page.events.length) setEvents((current) => [...current, ...page.events])
      setCursor(page.next_seq)
    }).catch((err) => setError(String(err)))
  }, [token, job?.id, job?.state, cursor])

  async function start(reset = false) {
    try {
      const next = reset && job
        ? await call<Job>(token, `/jobs/${job.id}/reset`, {})
        : await call<Job>(token, '/jobs', { fixture_id: fixtureId, goal })
      setJob(next); setCopied(false); setEvents([]); setCursor(0); setError('')
    } catch (err) { setError(String(err)) }
  }

  async function downloadReport() {
    if (!job) return
    try {
      const report = await call<Record<string, unknown>>(token, `/jobs/${job.id}/report`)
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a'); link.href = url; link.download = `${job.id}-report.json`; link.click()
      URL.revokeObjectURL(url)
    } catch (err) { setError(String(err)) }
  }

  const gateEvents = events.filter((event) => event.detail_type === 'autopilot.gate')
  const latency = events.reduce((total, event) => total + (
    typeof event.detail.payload.latency_ms === 'number' ? event.detail.payload.latency_ms : 0
  ), 0)

  return <div className="autopilot space-y-6 text-text">
    <header className="autopilot-hero">
      <div><p className="eyebrow"><Sparkles size={13} aria-hidden="true" /> GOVERNED CODE EXECUTION</p><h1>AgentShield Autopilot</h1>
        <p className="mt-3 max-w-xl text-text-dim">From intent to a verified patch. Inspect every decision, test receipt, and code change in one auditable workspace.</p></div>
      <div className="engine-card"><span className="eyebrow text-violet-300">MODEL PROVENANCE</span><strong>{job?.model_id || 'Nebius coding engine'}</strong><span className={configured ? 'text-allow' : 'text-review'}>● {configured ? 'Provider configured' : 'Configuration not verified'}</span><small>Disposable Python fixtures · Docker test runner</small></div>
    </header>
    {configurationError && <section role="alert" className="rounded border border-amber-400/50 bg-ink-800 p-4">
      <h2 className="font-semibold">Autopilot setup required</h2>
      <p>{configurationError}</p>
      {configurationError.includes('NEBIUS_API_KEY') && <p className="mt-2 text-sm">Add <code>NEBIUS_API_KEY</code> to <code>services/api/.env</code> or export it in your API shell, restart the backend, then load fixtures again. Keep your demo token configured.</p>}
    </section>}
    <div className="autopilot-setup console-panel">
      <div className="section-heading"><div><p className="eyebrow">01 / CONFIGURATION</p><h2>Define the coding job</h2></div><LockKeyhole size={18} className="text-text-dim" aria-hidden="true" /></div>
      <label>Demo token <input aria-label="Demo token" type="password" value={token} onChange={(event) => setToken(event.target.value)} className="autopilot-input" /></label>
      <button onClick={() => void loadFixtures()} className="console-secondary w-fit">Load fixtures</button>
      {fixtures.length > 0 && <>
        <label>Fixture <select value={fixtureId} onChange={(event) => {
          const next = fixtures.find((fixture) => fixture.fixture_id === event.target.value)
          setFixtureId(event.target.value); setGoal(next?.suggested_goal ?? '')
        }} className="autopilot-input">
          {fixtures.map((fixture) => <option key={fixture.fixture_id} value={fixture.fixture_id}>{fixture.name}</option>)}
        </select></label>
        <p className="text-sm text-text-dim">{fixtures.find((fixture) => fixture.fixture_id === fixtureId)?.description}</p>
        <p className="text-sm text-text-dim">Policy probes cover allowed source/test reads, path traversal, absolute paths, and secret-file access. Run the offline evaluator to inspect all ten outcomes.</p>
        <label>Goal <textarea value={goal} onChange={(event) => setGoal(event.target.value)} maxLength={2000} rows={3} className="autopilot-input block w-full resize-y" /></label>
        <button disabled={!configured || (!!job && !terminal.has(job.state)) || !goal.trim()} onClick={() => void start()} className="console-primary w-fit">{job && !terminal.has(job.state) ? <Loader2 size={15} className="animate-spin" aria-hidden="true" /> : <Play size={15} aria-hidden="true" />}Start coding job</button>
      </>}
    </div>
    {error && <p role="alert" className="text-red-400">{error}</p>}
    {!job && <section className="autopilot-empty console-panel"><ShieldCheck size={28} className="text-shield" aria-hidden="true" /><h2>Your next patch starts here</h2><p>Load a fixture, review the goal, then start a coding job.<br />Gate decisions, test evidence, and the patch will appear below.</p><div><span>01 · Configure</span><span>02 · Govern</span><span>03 · Verify</span></div></section>}
    {job && <>
      <section className="job-summary console-panel p-5">
        <h2 className="text-xl font-semibold">{job.state} {job.verified ? '· verified' : '· not verified'}</h2>
        <p className="font-mono text-xs">{job.id}</p>
        <p className="model-provenance">Provider: {job.model_id ? `Nebius · ${job.model_id}` : 'waiting for live model'}</p>
        <div className="job-metrics"><p>Tokens: {job.tokens_in} in / {job.tokens_out} out · {job.tool_calls} tools · {job.repair_rounds} repairs</p>
        <p>Model latency: {(latency / 1000).toFixed(2)} s total</p></div>
        <div className="mt-2 flex flex-wrap gap-2">{[1, 2].map((gate) => {
          const latest = gateEvents.filter((event) => event.detail.payload.gate === gate).at(-1)
          const decision = String(latest?.detail.payload.decision ?? 'waiting')
          return <span key={gate} className={`rounded border px-3 py-1 text-sm ${decision === 'block' ? 'border-block/40 bg-block-subtle text-block' : decision === 'allow' ? 'border-allow/40 bg-allow-subtle text-allow' : 'border-review/40 bg-review-subtle text-review'}`}>Gate {gate}: {decision}</span>
        })}</div>
        {job.error && <p role="alert" className="text-red-400">{job.error}</p>}
        {terminal.has(job.state) && <div className="mt-3 flex gap-3">
          <button disabled={!configured} onClick={() => void start(true)} className="console-primary">Reset and run again</button>
          <button onClick={() => void downloadReport()} className="console-secondary"><Download size={15} aria-hidden="true" />Download report</button>
        </div>}
      </section>
      <div className="grid gap-4 md:grid-cols-2"><Receipt title="Before tests" result={job.baseline} /><Receipt title="After tests" result={job.after} /></div>
      <section className="console-panel diff-panel"><div className="section-heading"><div><p className="eyebrow">02 / CODE CHANGES</p><h2>Patch diff</h2></div><button className="console-secondary" disabled={!job.diff} onClick={() => { void navigator.clipboard.writeText(job.diff).then(() => setCopied(true)).catch(() => setError('Could not copy diff. Select and copy the patch text.')) }}>{copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}{copied ? 'Copied' : 'Copy diff'}</button></div><pre className="diff-output max-h-96 overflow-auto p-4 text-xs">{job.diff ? job.diff.split('\n').map((line, index) => <span key={index} className={`diff-line block ${line.startsWith('+') ? 'bg-green-500/10 text-green-300' : line.startsWith('-') ? 'bg-red-500/10 text-red-300' : line.startsWith('@@') ? 'text-sky-300' : ''}`}>{line || ' '}</span>) : 'No patch yet'}</pre></section>
      <section className="console-panel audit-panel"><div className="section-heading"><div><p className="eyebrow">03 / EXECUTION TRACE</p><h2>Audit timeline</h2></div><span className="font-mono text-xs text-text-dim">{events.length} events</span></div>{events.length === 0 && <p className="p-5 text-text-dim">Waiting for execution events.</p>}<ol className="audit-timeline">
        {events.map((event) => <li key={event.detail.seq} className="audit-event">
          <strong><Terminal size={13} aria-hidden="true" /> #{event.detail.seq} {event.detail_type}</strong><pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(event.detail.payload, null, 2)}</pre>
        </li>)}
      </ol></section>
    </>}
  </div>
}
