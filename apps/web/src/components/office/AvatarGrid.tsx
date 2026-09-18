/**
 * The card-grid office. Required, not optional.
 *
 * Built **before** the Phaser scene, deliberately. It covers three real cases:
 * WebGL unavailable, the snapshot failing, and the visual phase running out of
 * time. It takes two hours, it de-risks the entire visual phase, and it proves
 * the store shape is right before any game code exists.
 *
 * It reads the identical `simStore` avatar state the canvas does, so the two
 * stay in sync with no extra wiring. It is also the accessible path to the
 * office: fully keyboard navigable, reachable from a `Simple view` toggle
 * rather than only as an error state.
 */

import { cn } from '@/lib/cn'
import { roleLabel } from '@/lib/format'
import { riskColor } from '@/lib/risk'
import { useSim } from '@/stores/simStore'
import type { AvatarState } from '@/lib/api'
import { EmptyState } from '@/components/ui'

const FSM_DOT: Record<AvatarState['fsm'], { color: string; glyph: string; label: string }> = {
  working: { color: 'bg-allow', glyph: '●', label: 'Working' },
  waiting: { color: 'bg-review', glyph: '⏳', label: 'Waiting' },
  blocked: { color: 'bg-block', glyph: '✕', label: 'Blocked' },
  idle: { color: 'bg-idle', glyph: '○', label: 'Idle' },
  walking: { color: 'bg-idle', glyph: '○', label: 'Idle' },
  meeting: { color: 'bg-shield', glyph: '◇', label: 'Meeting' },
}

export function AvatarGrid({ onSelect }: { onSelect: (employeeId: string) => void }) {
  const avatars = useSim((s) => s.avatars)
  const rows = Object.values(avatars).sort((a, b) => a.employee_id.localeCompare(b.employee_id))

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No employees in this run."
        hint="Seed a run to populate the floor."
      />
    )
  }

  return (
    <div
      className="grid gap-3 p-4"
      style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}
      role="list"
      aria-label={ariaSummary(rows)}
    >
      {rows.map((avatar) => (
        <AvatarCard key={avatar.employee_id} avatar={avatar} onSelect={onSelect} />
      ))}
    </div>
  )
}

function AvatarCard({
  avatar,
  onSelect,
}: {
  avatar: AvatarState
  onSelect: (employeeId: string) => void
}) {
  const state = FSM_DOT[avatar.fsm]
  const flagged = avatar.badge === 'anomaly'

  return (
    <div
      role="listitem"
      tabIndex={0}
      onClick={() => onSelect(avatar.employee_id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(avatar.employee_id)
        }
      }}
      className={cn(
        'cursor-pointer rounded-md border bg-ink-800 p-4 transition-colors duration-100',
        'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
        flagged ? 'border-anomaly/40' : 'border-line hover:border-line-strong',
      )}
    >
      <div className="flex items-start gap-2">
        <div className="h-8 w-8 shrink-0 rounded-sm bg-ink-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate font-ui text-[13px] font-medium text-text">{avatar.name}</p>
          <p className="truncate font-ui text-[11px] text-text-dim">
            {roleLabel(avatar.role)}
          </p>
          <p className="truncate font-ui text-[11px] text-text-faint">{avatar.team}</p>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-1.5">
        {/* Glyph as well as colour: the four states stay distinguishable in
            greyscale and to colour-blind readers. */}
        <span className={cn('h-1.5 w-1.5 rounded-full', state.color)} aria-hidden />
        <span className="font-ui text-[11px] text-text-dim">{state.label}</span>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-xs bg-ink-700">
          <div
            className="h-full rounded-xs"
            style={{
              width: `${Math.max(2, avatar.risk_score)}%`,
              background: riskColor(avatar.risk_score),
            }}
          />
        </div>
        <span className="font-mono text-[11px] tabular-nums text-text">
          {avatar.risk_score}
        </span>
      </div>

      {flagged && (
        <p className="mt-1.5 font-mono text-[10px] tracking-[0.04em] text-anomaly">
          ◆ FLAGGED
        </p>
      )}

      {avatar.current_task_title && (
        <p className="mt-2 truncate font-ui text-[11px] text-text-faint">
          {avatar.current_task_title}
        </p>
      )}
    </div>
  )
}

/**
 * The text equivalent of the floor.
 *
 * The canvas carries the same sentence in its `aria-label`, regenerated every
 * two seconds. A view that only exists as pixels is not a view everyone has.
 */
export function ariaSummary(avatars: AvatarState[]): string {
  const counts = avatars.reduce<Record<string, number>>((acc, avatar) => {
    const key = avatar.fsm === 'walking' ? 'idle' : avatar.fsm
    acc[key] = (acc[key] ?? 0) + 1
    return acc
  }, {})

  const parts = [
    counts.working && `${counts.working} working`,
    counts.waiting && `${counts.waiting} waiting for approval`,
    counts.blocked && `${counts.blocked} blocked`,
    counts.idle && `${counts.idle} idle`,
  ].filter(Boolean)

  return `Office floor: ${parts.join(', ') || 'no activity'}.`
}
