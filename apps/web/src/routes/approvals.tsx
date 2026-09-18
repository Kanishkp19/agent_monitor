/**
 * The approvals queue.
 *
 * `docs/01-PRD.md` states the manager's problem precisely: requests arrive
 * with no context, so they either rubber-stamp everything or become a
 * blocker. Every field on this card exists to make a five-second decision
 * possible -- especially the last one, "has deployed to prod 0 times in the
 * last 7 days", which turns a risk score into a judgement.
 *
 * Keyboard: `j`/`k` move between cards, `a` approves, `d` denies.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/cn'
import { endpoints, type ApprovalCard as ApprovalCardData } from '@/lib/api'
import { formatCountdown, formatMoney, roleLabel } from '@/lib/format'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'
import { useUi } from '@/stores/uiStore'
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Panel,
  RiskMeter,
  Segmented,
  Skeleton,
  input,
  table,
} from '@/components/ui'

export default function ApprovalsRoute() {
  const run = useSim((s) => s.run)
  const simTs = useSim((s) => s.simTs)
  const toast = useUi((s) => s.toast)
  const events = useTelemetry((s) => s.events)

  const [tab, setTab] = useState<'pending' | 'decided'>('pending')
  const [cards, setCards] = useState<ApprovalCardData[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [focused, setFocused] = useState(0)
  const [denying, setDenying] = useState<string | null>(null)
  const [note, setNote] = useState('')

  const load = useCallback(async () => {
    if (!run) return
    try {
      setError(null)
      setCards(await endpoints.approvals(run.id, tab))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [run, tab])

  useEffect(() => {
    void load()
  }, [load])

  // Poll as a floor, but invalidate immediately on the WebSocket event. A
  // five-second poll alone would make an approval feel slow precisely when
  // someone is watching for it.
  useEffect(() => {
    const timer = window.setInterval(() => void load(), 5000)
    return () => window.clearInterval(timer)
  }, [load])

  useEffect(() => {
    const latest = events[events.length - 1]
    if (
      latest &&
      (latest.detail_type === 'approval.requested' ||
        latest.detail_type === 'approval.decided')
    ) {
      void load()
    }
  }, [events, load])

  const decide = useCallback(
    async (card: ApprovalCardData, decision: string, withNote?: string) => {
      if (!run) return
      const approverId = card.requester.id === 'emp_003' ? 'emp_002' : 'emp_003'
      try {
        await endpoints.decide(run.id, card.approval.id, {
          decision,
          approver_id: approverId,
          note: withNote ?? null,
        })
        setCards((current) =>
          (current ?? []).filter((c) => c.approval.id !== card.approval.id),
        )
        toast(
          decision === 'deny' ? 'neutral' : 'success',
          decision === 'deny'
            ? 'Denied. The task was terminated.'
            : `Approved — ${card.requester.name}'s ${card.action.tool} is continuing.`,
        )
        setDenying(null)
        setNote('')
      } catch (e) {
        const message = (e as Error).message
        toast('error', message.includes('already') ? 'Someone already decided this.' : message)
        void load()
      }
    },
    [run, toast, load],
  )

  useKeyboardQueue(cards ?? [], focused, setFocused, decide, setDenying)

  return (
    <div className="flex flex-col gap-4">
      <Segmented
        value={tab}
        onChange={setTab}
        options={[
          { value: 'pending', label: `Pending${cards && tab === 'pending' ? ` (${cards.length})` : ''}` },
          { value: 'decided', label: 'Decided today' },
        ]}
      />

      {error && <ErrorState title="Couldn't load approvals." detail={error} onRetry={load} />}

      {!error && cards === null && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full rounded-md" />
          ))}
        </div>
      )}

      {!error && cards?.length === 0 && (
        <Panel>
          <EmptyState
            icon={ShieldCheck}
            title="Nothing waiting on you."
            hint="Approval requests appear here the moment a policy holds an action."
          />
        </Panel>
      )}

      {tab === 'decided' && cards && cards.length > 0 && <DecidedTable cards={cards} />}

      {tab === 'pending' &&
        cards?.map((card, index) => (
          <ApprovalCard
            key={card.approval.id}
            card={card}
            simTs={simTs}
            focused={index === focused}
            denying={denying === card.approval.id}
            note={note}
            onNote={setNote}
            onFocus={() => setFocused(index)}
            onDecide={(decision, withNote) => decide(card, decision, withNote)}
            onStartDeny={() => setDenying(card.approval.id)}
            onCancelDeny={() => setDenying(null)}
          />
        ))}
    </div>
  )
}

function ApprovalCard({
  card,
  simTs,
  focused,
  denying,
  note,
  onNote,
  onFocus,
  onDecide,
  onStartDeny,
  onCancelDeny,
}: {
  card: ApprovalCardData
  simTs: number
  focused: boolean
  denying: boolean
  note: string
  onNote: (value: string) => void
  onFocus: () => void
  onDecide: (decision: string, note?: string) => void
  onStartDeny: () => void
  onCancelDeny: () => void
}) {
  const navigate = useNavigate()
  const remaining = card.approval.expires_sim_ts - simTs
  const expired = remaining <= 0
  const rate = card.context.requester_7d_rate_for_tool

  return (
    <Card
      attention
      className={cn(focused && 'shadow-[var(--shadow-focus)]', expired && 'opacity-50')}
      onClick={onFocus}
    >
      <header className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <span className="text-review" aria-hidden>
            ⚠
          </span>
          <div>
            <p className="font-ui text-[13px] font-medium text-text">
              {card.requester.name}
            </p>
            <p className="font-ui text-[11px] text-text-dim">
              {roleLabel(card.requester.role)} · {card.requester.team}
            </p>
          </div>
        </div>
        <span className="font-mono text-[11px] tabular-nums text-review">
          {expired ? 'EXPIRED' : `expires ${formatCountdown(remaining)}`}
        </span>
      </header>

      <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
        <dt className="font-ui text-[11px] text-text-faint">The agent wants to</dt>
        <dd className="font-mono text-[12px] text-text">
          {card.action.tool} {card.action.target_resource}
        </dd>

        <dt className="font-ui text-[11px] text-text-faint">Environment</dt>
        <dd
          className={cn(
            'font-mono text-[12px]',
            card.action.environment === 'production' ? 'text-block' : 'text-text',
          )}
        >
          {card.action.environment.toUpperCase()}
        </dd>

        <dt className="font-ui text-[11px] text-text-faint">Why you&apos;re seeing it</dt>
        <dd className="font-ui text-[12px] text-text-dim">
          {card.context.reason}
          {card.context.policy_id && (
            <span className="ml-1 font-mono text-[11px] text-text-faint">
              ({card.context.policy_id})
            </span>
          )}
        </dd>
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-6 border-t border-line pt-3">
        <div className="flex items-center gap-2">
          <span className="font-ui text-[11px] text-text-faint">Risk</span>
          <RiskMeter score={card.approval.risk_at_request} width="w-20" />
        </div>
        <span className="font-mono text-[12px] tabular-nums text-spend">
          Session {formatMoney(card.context.cost_so_far_usd)}
        </span>
        {/* The number that turns a score into a decision. */}
        <span className="font-ui text-[12px] text-text-dim">
          {card.requester.name.split(' ')[0]} has done this{' '}
          <span className="font-mono tabular-nums text-text">{rate}</span>{' '}
          {rate === 1 ? 'time' : 'times'} in the last 7 days.
        </span>
      </div>

      {denying ? (
        <div className="mt-4 border-t border-line pt-3">
          <label className={input.label} htmlFor={`note-${card.approval.id}`}>
            Deny this {card.action.tool}?
          </label>
          <p className="mb-2 font-ui text-[12px] text-text-dim">
            The task will end and the agent will be told why.
          </p>
          <input
            id={`note-${card.approval.id}`}
            className={input.text}
            maxLength={500}
            placeholder="Optional note to the requester"
            value={note}
            onChange={(e) => onNote(e.target.value)}
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button variant="ghost" onClick={onCancelDeny}>
              Cancel
            </Button>
            <Button variant="deny" onClick={() => onDecide('deny', note)}>
              Deny
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
          <Button variant="ghost" onClick={() => navigate(`/live/${card.approval.task_id}`)}>
            View task
          </Button>
          <div className="flex gap-2">
            <Button variant="deny" onClick={onStartDeny} disabled={expired}>
              Deny
            </Button>
            <Button
              variant="approve"
              onClick={() => onDecide('approve_once')}
              disabled={expired}
            >
              Approve once
            </Button>
            <Button
              variant="approve"
              onClick={() => onDecide('approve_session')}
              disabled={expired}
              title="Allows this same action for the rest of this task only"
            >
              Approve session
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}

function DecidedTable({ cards }: { cards: ApprovalCardData[] }) {
  return (
    <div className={table.wrapper}>
      <table className="w-full border-collapse">
        <thead className={table.head}>
          <tr>
            <th scope="col" className={table.th}>
              Requester
            </th>
            <th scope="col" className={table.th}>
              Action
            </th>
            <th scope="col" className={table.th}>
              Decision
            </th>
            <th scope="col" className={table.th}>
              Note
            </th>
          </tr>
        </thead>
        <tbody>
          {cards.map((card) => (
            <tr key={card.approval.id} className="border-b border-line/60">
              <td className={table.cell}>{card.requester.name}</td>
              <td className={table.cell}>
                {card.action.tool} {card.action.target_resource}
              </td>
              <td className={table.cell}>{card.approval.status}</td>
              <td className={cn(table.cell, 'text-text-dim')}>
                {card.approval.note ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function useKeyboardQueue(
  cards: ApprovalCardData[],
  focused: number,
  setFocused: (index: number) => void,
  decide: (card: ApprovalCardData, decision: string) => void,
  setDenying: (id: string | null) => void,
) {
  const cardsRef = useRef(cards)
  cardsRef.current = cards

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return

      const list = cardsRef.current
      const card = list[focused]

      switch (event.key) {
        case 'j':
          setFocused(Math.min(focused + 1, list.length - 1))
          break
        case 'k':
          setFocused(Math.max(focused - 1, 0))
          break
        case 'a':
          if (card) decide(card, 'approve_once')
          break
        case 'd':
          if (card) setDenying(card.approval.id)
          break
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focused, setFocused, decide, setDenying])
}
