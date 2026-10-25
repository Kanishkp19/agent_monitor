/**
 * The Sandbox: feel the rulebook in one minute, no sign-in.
 *
 * Pick a role, type what you would ask a coding agent, pick a model tier --
 * the exact gates the office runs decide the outcome and *show their
 * reasons*. Gate 1 for the request, then any tool call goes through Gate 2
 * and the same simulated sandbox the bots use. `demo-<role>` is the whole
 * auth model: identity comes from the credential, never the body, exactly
 * like Live Mode.
 */

import { useCallback, useEffect, useState } from 'react'

import { cn } from '@/lib/cn'
import {
  type ApiError,
  playground,
  type PlaygroundContext,
  type PlaygroundDecision,
} from '@/lib/api'
import { useSim } from '@/stores/simStore'
import {
  Button,
  DecisionChip,
  EmptyState,
  ErrorState,
  SkeletonRows,
  input,
} from '@/components/ui'

const fieldInput = input.text
const selectInput = input.select

interface TraceStep {
  kind: 'gate1' | 'tool'
  label: string
  detail?: string
  decision: PlaygroundDecision
}

export default function SandboxRoute() {
  const run = useSim((s) => s.run)
  const [ctx, setCtx] = useState<PlaygroundContext | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [role, setRole] = useState('engineering_intern')
  const [model, setModel] = useState('auto')
  const [repo, setRepo] = useState('payments-api')
  const [environment, setEnvironment] = useState('local')
  const [prompt, setPrompt] = useState('Fix the null-amount bug in the payment handler.')
  const [busy, setBusy] = useState(false)
  const [trace, setTrace] = useState<TraceStep[]>([])

  useEffect(() => {
    playground
      .context()
      .then(setCtx)
      .catch((e) => setLoadError((e as Error).message))
  }, [])

  const submit = useCallback(async () => {
    if (!prompt.trim() || busy) return
    setBusy(true)
    try {
      const gate1 = await playground.gate1({
        role,
        task_type: 'bug_fix',
        complexity: 'standard',
        repo,
        environment,
        prompt,
        requested_model: model === 'auto' ? undefined : model,
      })
      setTrace((t) => [
        { kind: 'gate1', label: 'Gate 1 · request governance', decision: gate1 },
        ...t,
      ])
    } catch (e) {
      setTrace((t) => [
        {
          kind: 'gate1',
          label: 'Gate 1 · request governance',
          decision: {
            decision: 'block',
            reason: (e as ApiError).message ?? 'request failed',
            reason_code: 'request_error',
            policy_ids: [],
            matched_policies: [],
            task_id: '',
          },
        },
        ...t,
      ])
    } finally {
      setBusy(false)
    }
  }, [role, model, repo, environment, prompt, busy])

  const tryTool = useCallback(
    async (tool: string, args: Record<string, unknown>) => {
      if (busy) return
      setBusy(true)
      try {
        const created = await playground.createTask({
          role,
          title: prompt.slice(0, 80) || 'Playground task',
          repo,
          environment,
        })
        const outcome = await playground.tool({
          role,
          task_id: created.task_id,
          tool,
          args,
        })
        setTrace((t) => [
          {
            kind: 'tool',
            label: `Gate 2 · ${tool}`,
            detail: outcome.target_resource,
            decision: outcome,
          },
          ...t,
        ])
      } catch (e) {
        setTrace((t) => [
          {
            kind: 'tool',
            label: `Gate 2 · ${tool}`,
            decision: {
              decision: 'block',
              reason: (e as ApiError).message ?? 'request failed',
              reason_code: 'request_error',
              policy_ids: [],
              matched_policies: [],
              task_id: '',
            },
          },
          ...t,
        ])
      } finally {
        setBusy(false)
      }
    },
    [role, repo, environment, prompt, busy],
  )

  if (loadError) {
    return <ErrorState title="The playground could not load." detail={loadError} />
  }
  if (!ctx) {
    return <SkeletonRows rows={6} />
  }

  const roleSpec = ctx.roles.find((r) => r.id === role)

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="font-ui text-[20px] font-semibold leading-7 tracking-[-0.01em] text-text">
          Sandbox
        </h1>
        <p className="mt-1 max-w-3xl font-ui text-[13px] leading-5 text-text-dim">
          Try the governance gates without signing in. You are governed exactly
          as that role is in the office — same policies, same precedence
          (block &gt; review &gt; redact &gt; allow), same simulated sandbox.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[380px_1fr]">
        {/* ── Controls ─────────────────────────────────────────── */}
        <section className="flex flex-col gap-3 rounded-md border border-line bg-ink-800 p-4">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
              Your role
            </span>
            <select
              className={selectInput}
              value={role}
              onChange={(e) => setRole(e.target.value)}
            >
              {ctx.roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                  {r.prod_access ? ' · prod' : ''}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
              Model tier
            </span>
            <select
              className={selectInput}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {ctx.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
                Repo
              </span>
              <select className={selectInput} value={repo} onChange={(e) => setRepo(e.target.value)}>
                {ctx.repos.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
                Environment
              </span>
              <select
                className={selectInput}
                value={environment}
                onChange={(e) => setEnvironment(e.target.value)}
              >
                {ctx.environments.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
              Prompt to the coding agent
            </span>
            <textarea
              className={cn(fieldInput, 'min-h-[96px] resize-y')}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g. Deploy the settlement fix to production"
            />
          </label>

          <Button variant="primary" onClick={() => void submit()} disabled={busy}>
            {busy ? 'Govern…' : 'Run through Gate 1'}
          </Button>

          <div className="mt-1 border-t border-line pt-3">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-faint">
              …or attempt one tool call (Gate 2 + sandbox)
            </span>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {[
                { label: 'Read .env.production', tool: 'read_file', args: { path: '.env.production' } },
                { label: 'Read handler', tool: 'read_file', args: { path: 'src/handlers/payment.py' } },
                { label: 'Deploy → production', tool: 'deploy', args: { environment: 'production' } },
                { label: 'Push main', tool: 'git_push', args: { branch: 'main' } },
                { label: 'Run unit tests', tool: 'run_tests', args: { suite: 'unit' } },
                { label: 'Fetch external', tool: 'external_fetch', args: { url: 'https://example.com/feed' } },
              ].map(({ label, tool, args }) => (
                <Button
                  key={label}
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void tryTool(tool, args)}
                  className="justify-start text-left text-[12px]"
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </section>

        {/* ── Trace ────────────────────────────────────────────── */}
        <section className="flex min-h-0 flex-col gap-3">
          <div className="rounded-md border border-line bg-ink-800 px-4 py-3 font-ui text-[12px] leading-5 text-text-dim">
            <span className="font-medium text-text">Governed as:</span>{' '}
            {roleSpec?.label ?? role}
            <span className="mx-2 text-text-faint">·</span>
            prod access {roleSpec?.prod_access ? 'granted' : 'denied'}
            <span className="mx-2 text-text-faint">·</span>
            run {run?.id ?? '—'}
          </div>

          {trace.length === 0 ? (
            <EmptyState
              title="No decisions yet."
              hint="Run the prompt through Gate 1, or attempt a tool call on the left."
            />
          ) : (
            <ol className="flex flex-col gap-2">
              {trace.map((step, i) => (
                <li
                  key={`${step.kind}-${i}`}
                  className="rounded-md border border-line bg-ink-800 p-3"
                >
                  <div className="flex items-center gap-2">
                    <DecisionChip decision={step.decision.decision} />
                    <span className="font-ui text-[13px] font-medium text-text">
                      {step.label}
                    </span>
                    {step.detail ? (
                      <span className="font-mono text-[11px] text-text-dim">{step.detail}</span>
                    ) : null}
                  </div>
                  <p className="mt-1.5 font-ui text-[12px] leading-5 text-text-dim">
                    {step.decision.reason}
                  </p>
                  {step.decision.policy_ids.length > 0 ? (
                    <p className="mt-1 font-mono text-[11px] text-text-faint">
                      matched: {step.decision.policy_ids.join(', ')}
                    </p>
                  ) : null}
                  {step.decision.routed_model ? (
                    <p className="mt-1 font-mono text-[11px] text-text-faint">
                      routed model: {step.decision.routed_model}
                      {step.decision.est_cost_usd !== undefined
                        ? ` · est $${step.decision.est_cost_usd.toFixed(4)}`
                        : ''}
                    </p>
                  ) : null}
                  {step.decision.redacted ? (
                    <p className="mt-1 font-ui text-[12px] text-redact">
                      Secret found — prompt returned redacted.
                    </p>
                  ) : null}
                  {step.decision.approval_id ? (
                    <p className="mt-1 font-ui text-[12px] text-review">
                      approval_id: <span className="font-mono">{step.decision.approval_id}</span> —
                      decide it on the Approvals page.
                    </p>
                  ) : null}
                  {step.decision.result ? (
                    <pre className="mt-2 max-h-40 overflow-auto rounded bg-ink-900 p-2 font-mono text-[11px] leading-4 text-text-dim">
                      {step.decision.result.error
                        ? String(step.decision.result.error)
                        : step.decision.result.output || '(empty output)'}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  )
}
