/**
 * The policy list and editor.
 *
 * Two details carry most of the weight here:
 *
 * - **The 24h match count.** A policy list without it is a list of intentions.
 *   The rule that has matched zero times today is either dead weight or a
 *   control that is not working, and both are worth knowing.
 * - **Validation names the JSON path.** `when.all[1].field — unknown field
 *   "actor.department". Did you mean "actor.team"?` rather than "Invalid
 *   input". The server produces that message; the editor just renders it.
 */

import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { type ApiError, endpoints, type Policy } from '@/lib/api'
import { useSim } from '@/stores/simStore'
import { useUi } from '@/stores/uiStore'
import {
  Button,
  DecisionChip,
  Drawer,
  EmptyState,
  ErrorState,
  Segmented,
  SkeletonRows,
  input,
  table,
  type Decision,
} from '@/components/ui'

export default function PoliciesRoute() {
  const navigate = useNavigate()
  const run = useSim((s) => s.run)
  const toast = useUi((s) => s.toast)

  const [policies, setPolicies] = useState<Policy[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Policy | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      setPolicies(await endpoints.policies(run?.id))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [run])

  useEffect(() => {
    void load()
  }, [load])

  const toggle = async (policy: Policy) => {
    try {
      await endpoints.togglePolicy(policy.id, !policy.enabled)
      toast('success', `${policy.name} is now ${policy.enabled ? 'off' : 'on'}.`)
      void load()
    } catch (e) {
      toast('error', (e as Error).message)
    }
  }

  const active = policies?.filter((p) => !p.is_draft).length ?? 0
  const drafts = policies?.filter((p) => p.is_draft).length ?? 0

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between">
        <h1 className="font-ui text-[20px] font-semibold leading-7 tracking-[-0.01em] text-text">
          Policies{' '}
          <span className="font-ui text-[13px] font-normal text-text-dim">
            ({active} active, {drafts} draft)
          </span>
        </h1>
        <Button variant="primary" onClick={() => setEditing(blankPolicy())}>
          + New policy
        </Button>
      </header>

      {error && <ErrorState title="Couldn't load policies." detail={error} onRetry={load} />}

      {!error && (
        <div className={table.wrapper}>
          <table className="w-full border-collapse">
            <thead className={table.head}>
              <tr>
                <th scope="col" className={cn(table.th, 'w-12')}>
                  On
                </th>
                <th scope="col" className={table.th}>
                  Name
                </th>
                <th scope="col" className={cn(table.th, 'w-16')}>
                  Gate
                </th>
                <th scope="col" className={cn(table.th, 'w-24')}>
                  Effect
                </th>
                <th scope="col" className={cn(table.th, 'w-16')}>
                  Pri
                </th>
                <th scope="col" className={cn(table.th, 'w-16')}>
                  24h
                </th>
                <th scope="col" className={cn(table.th, 'w-16')}>
                  Ver
                </th>
              </tr>
            </thead>
            <tbody>
              {policies === null && <SkeletonRows rows={6} columns={7} />}

              {policies?.map((policy) => (
                <tr
                  key={policy.id}
                  className={table.row}
                  onClick={() => setEditing(policy)}
                >
                  <td className={table.cell}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        void toggle(policy)
                      }}
                      aria-label={policy.enabled ? 'Disable' : 'Enable'}
                      className={cn(
                        'text-[13px]',
                        policy.enabled ? 'text-allow' : 'text-text-faint',
                      )}
                    >
                      {policy.enabled ? '●' : '○'}
                    </button>
                  </td>
                  <td className={cn(table.cell, 'font-ui text-[13px]')}>{policy.name}</td>
                  <td className={table.cell}>{policy.gate}</td>
                  <td className={table.cell}>
                    <DecisionChip decision={policy.effect as Decision} />
                  </td>
                  <td className={table.cell}>{policy.priority}</td>
                  <td className={cn(table.cell, 'text-text-dim')}>
                    {policy.match_count_24h ?? '—'}
                  </td>
                  <td className={cn(table.cell, 'text-text-faint')}>
                    {policy.is_draft ? 'draft' : `v${policy.version}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {policies?.length === 0 && (
            <EmptyState
              title="No policies yet."
              hint="The starter set is twelve rules covering secrets, production and spend."
              action={
                <Button variant="primary" onClick={load}>
                  Add the starter set
                </Button>
              }
            />
          )}
        </div>
      )}

      {editing && (
        <PolicyEditor
          policy={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            void load()
          }}
          onTest={(policy) =>
            navigate('/control/policy-lab', { state: { draft: policy } })
          }
        />
      )}
    </div>
  )
}

function PolicyEditor({
  policy,
  onClose,
  onSaved,
  onTest,
}: {
  policy: Policy
  onClose: () => void
  onSaved: () => void
  onTest: (policy: Policy) => void
}) {
  const toast = useUi((s) => s.toast)
  const [draft, setDraft] = useState<Policy>(policy)
  const [conditionText, setConditionText] = useState(
    JSON.stringify(policy.when, null, 2),
  )
  const [validation, setValidation] = useState<{ field?: string; message: string } | null>(
    null,
  )
  const [fields, setFields] = useState<string[]>([])

  useEffect(() => {
    endpoints
      .policyFields()
      .then((data) => setFields(draft.gate === 1 ? data.gate1 : data.gate2))
      .catch(() => setFields([]))
  }, [draft.gate])

  // Debounced live validation. 400ms is long enough not to fire on every
  // keystroke and short enough that the error appears while the mistake is
  // still on screen.
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      let parsed: unknown
      try {
        parsed = JSON.parse(conditionText)
      } catch (e) {
        setValidation({ message: `Not valid JSON: ${(e as Error).message}` })
        return
      }

      try {
        await endpoints.validatePolicy(parsed, draft.gate)
        setValidation(null)
      } catch (e) {
        const error = e as ApiError
        setValidation({ field: error.field, message: error.message })
      }
    }, 400)

    return () => window.clearTimeout(timer)
  }, [conditionText, draft.gate])

  const save = async (asDraft: boolean) => {
    if (validation) {
      toast('error', `${validation.message}${validation.field ? ` at ${validation.field}` : ''}`)
      return
    }

    const body = {
      name: draft.name,
      gate: draft.gate,
      priority: draft.priority,
      effect: draft.effect,
      enabled: !asDraft,
      is_draft: asDraft,
      when: JSON.parse(conditionText) as Record<string, unknown>,
      approver: draft.effect === 'review' ? draft.approver : null,
      ttl_sim_seconds: draft.ttl_sim_seconds,
      route_override: draft.route_override,
      message: draft.message,
    }

    try {
      // An edit creates version N+1 and repoints CURRENT; the old version
      // stays, because the Policy Lab replays against whichever version was
      // live at the time.
      const saved = draft.id
        ? await endpoints.patchPolicy(draft.id, body)
        : await endpoints.createPolicy(body)

      toast(
        'success',
        asDraft
          ? 'Saved as a draft. Drafts are never evaluated by live gates.'
          : `Policy saved as v${saved.version}. Active on the next evaluation.`,
      )
      onSaved()
    } catch (e) {
      const error = e as ApiError
      toast('error', `${error.message}${error.field ? ` at ${error.field}` : ''}`)
    }
  }

  return (
    <Drawer open onClose={onClose} width="w-[640px]">
      <div className="p-5">
        <header className="flex items-start justify-between">
          <h2 className="font-ui text-[15px] font-semibold text-text">
            {policy.id ? 'Edit policy' : 'New policy'}
          </h2>
          <button onClick={onClose} className="text-text-faint hover:text-text">
            ✕
          </button>
        </header>

        <div className="mt-4 space-y-4">
          <div>
            <label className={input.label} htmlFor="policy-name">
              Name
            </label>
            <input
              id="policy-name"
              className={input.text}
              value={draft.name}
              minLength={3}
              maxLength={80}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </div>

          <div className="flex gap-4">
            <div>
              <span className={input.label}>Gate</span>
              <Segmented
                value={draft.gate}
                onChange={(gate) => setDraft({ ...draft, gate })}
                options={[
                  { value: 1, label: 'Gate 1 (request)' },
                  { value: 2, label: 'Gate 2 (action)' },
                ]}
              />
            </div>
            <div>
              <span className={input.label}>Effect</span>
              <Segmented
                value={draft.effect}
                onChange={(effect) => setDraft({ ...draft, effect })}
                options={[
                  { value: 'allow', label: 'allow' },
                  {
                    value: 'redact',
                    label: 'redact',
                    // There is no partial read of a secret file.
                    disabled: draft.gate === 2,
                    title:
                      draft.gate === 2 ? 'Redact is not available at Gate 2' : undefined,
                  },
                  { value: 'review', label: 'review' },
                  { value: 'block', label: 'block' },
                ]}
              />
            </div>
            <div className="w-24">
              <label className={input.label} htmlFor="policy-priority">
                Priority
              </label>
              <input
                id="policy-priority"
                type="number"
                min={0}
                max={999}
                className={cn(input.text, 'font-mono tabular-nums')}
                value={draft.priority}
                onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) })}
              />
            </div>
          </div>

          {draft.effect === 'review' && (
            <div className="flex gap-4">
              <div className="flex-1">
                <label className={input.label} htmlFor="policy-approver">
                  Approver role
                </label>
                <select
                  id="policy-approver"
                  className={cn(input.select, 'w-full')}
                  value={draft.approver?.role ?? 'manager'}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      approver: { role: e.target.value, scope: draft.approver?.scope ?? 'team' },
                    })
                  }
                >
                  {['manager', 'senior_manager', 'senior_engineer', 'devops'].map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
              <div className="w-32">
                <label className={input.label} htmlFor="policy-ttl">
                  TTL (sim s)
                </label>
                <input
                  id="policy-ttl"
                  type="number"
                  min={30}
                  max={86400}
                  className={cn(input.text, 'font-mono tabular-nums')}
                  value={draft.ttl_sim_seconds}
                  onChange={(e) =>
                    setDraft({ ...draft, ttl_sim_seconds: Number(e.target.value) })
                  }
                />
              </div>
            </div>
          )}

          <div>
            <label className={input.label} htmlFor="policy-message">
              Message
            </label>
            <input
              id="policy-message"
              className={input.text}
              maxLength={200}
              value={draft.message}
              onChange={(e) => setDraft({ ...draft, message: e.target.value })}
            />
            <p className={input.helper}>
              Shown to the requester and on the approval card.
            </p>
          </div>

          <div>
            <label className={input.label} htmlFor="policy-condition">
              Condition
            </label>
            <textarea
              id="policy-condition"
              rows={12}
              spellCheck={false}
              aria-invalid={validation !== null}
              className={cn(
                input.text,
                'h-auto resize-y py-2 font-mono text-[12px] leading-5',
                validation && 'border-block shadow-[0_0_0_1px_var(--color-block)]',
              )}
              value={conditionText}
              onChange={(e) => setConditionText(e.target.value)}
            />
            {validation ? (
              <p className={input.error}>
                {validation.field && (
                  <span className="font-mono">{validation.field} — </span>
                )}
                {validation.message}
              </p>
            ) : (
              <p className={input.helper}>
                {fields.length} fields available for Gate {draft.gate}.
              </p>
            )}
          </div>
        </div>

        <footer className="mt-5 flex items-center justify-between border-t border-line pt-4">
          <Button variant="ghost" onClick={() => onTest(draft)}>
            Test against last 24h
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => void save(true)}>
              Save as draft
            </Button>
            <Button variant="primary" onClick={() => void save(false)}>
              Save and enable
            </Button>
          </div>
        </footer>
      </div>
    </Drawer>
  )
}

function blankPolicy(): Policy {
  return {
    id: '',
    version: 0,
    name: '',
    gate: 2,
    priority: 50,
    effect: 'review',
    enabled: true,
    is_draft: false,
    when: { all: [{ field: 'action.tool', op: 'eq', value: 'deploy' }] },
    approver: { role: 'manager', scope: 'team' },
    ttl_sim_seconds: 300,
    route_override: null,
    message: '',
  }
}
