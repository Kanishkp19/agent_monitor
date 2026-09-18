/**
 * The component library.
 *
 * Every class string here comes from `docs/04-UI-UX-BRIEF.md` section 5.
 * Nothing is invented, and no raw hex appears anywhere -- colour comes from
 * the `@theme` tokens, because in this product a colour is a claim about
 * state, not a decoration.
 *
 * Kept in one file on purpose: these are small, they are used together, and
 * eighteen two-line files would be harder to keep consistent than one list
 * you can read top to bottom.
 */

import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

import { cn } from '@/lib/cn'
import { riskColor } from '@/lib/risk'

// ──────────────────────────────────────────────────────────────────────
// Buttons
// ──────────────────────────────────────────────────────────────────────

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'approve' | 'deny' | 'icon'

const BUTTON: Record<ButtonVariant, string> = {
  primary:
    'inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-shield text-white font-ui ' +
    'text-[13px] font-medium hover:bg-shield-hover active:translate-y-px ' +
    'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)] ' +
    'disabled:bg-ink-700 disabled:text-text-faint disabled:cursor-not-allowed ' +
    'transition-colors duration-100',
  secondary:
    'inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-ink-700 text-text ' +
    'border border-line font-ui text-[13px] font-medium hover:bg-ink-600 ' +
    'hover:border-line-strong active:translate-y-px focus-visible:outline-none ' +
    'focus-visible:shadow-[var(--shadow-focus)] disabled:text-text-faint ' +
    'disabled:cursor-not-allowed transition-colors duration-100',
  ghost:
    'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-sm text-text-dim font-ui ' +
    'text-[13px] hover:bg-ink-700 hover:text-text focus-visible:outline-none ' +
    'focus-visible:shadow-[var(--shadow-focus)] transition-colors duration-100',
  // The only green button in the product.
  approve:
    'inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-allow-subtle text-allow ' +
    'border border-allow/40 font-ui text-[13px] font-medium hover:bg-allow ' +
    'hover:text-ink-950 hover:border-allow focus-visible:outline-none ' +
    'focus-visible:shadow-[var(--shadow-focus)] transition-colors duration-100',
  deny:
    'inline-flex items-center gap-1.5 h-8 px-3 rounded-sm bg-transparent text-block ' +
    'border border-block/40 font-ui text-[13px] font-medium hover:bg-block-subtle ' +
    'hover:border-block focus-visible:outline-none ' +
    'focus-visible:shadow-[var(--shadow-focus)] transition-colors duration-100',
  icon:
    'inline-flex items-center justify-center h-8 w-8 rounded-sm text-text-dim ' +
    'hover:bg-ink-700 hover:text-text focus-visible:outline-none ' +
    'focus-visible:shadow-[var(--shadow-focus)] transition-colors duration-100',
}

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  loading?: boolean
}

export function Button({
  variant = 'secondary',
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn(BUTTON[variant], className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {/* The label stays put while loading. Swapping it for "Loading…" shifts
          the button's width, which is worse than the wait. */}
      {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
      {children}
    </button>
  )
}

// ──────────────────────────────────────────────────────────────────────
// Chips
// ──────────────────────────────────────────────────────────────────────

const CHIP_BASE =
  'inline-flex items-center h-5 px-1.5 rounded-xs border font-mono text-[10px] ' +
  'leading-none font-medium tracking-[0.04em]'

export type Decision = 'allow' | 'redact' | 'review' | 'block'

const DECISION_CHIP: Record<Decision, string> = {
  allow: 'bg-allow-subtle text-allow border-allow/30',
  redact: 'bg-redact-subtle text-redact border-redact/30',
  review: 'bg-review-subtle text-review border-review/30',
  block: 'bg-block-subtle text-block border-block/30',
}

export function DecisionChip({ decision }: { decision: Decision }) {
  return (
    <span className={cn(CHIP_BASE, DECISION_CHIP[decision])}>{decision.toUpperCase()}</span>
  )
}

const STATUS_CHIP: Record<string, { classes: string; glyph: string }> = {
  working: { classes: 'bg-allow-subtle text-allow border-allow/30', glyph: '●' },
  requesting: { classes: 'bg-allow-subtle text-allow border-allow/30', glyph: '●' },
  awaiting_approval: { classes: 'bg-review-subtle text-review border-review/30', glyph: '⏳' },
  blocked: { classes: 'bg-block-subtle text-block border-block/30', glyph: '●' },
  denied: { classes: 'bg-ink-700 text-block border-line', glyph: '✕' },
  denied_timeout: { classes: 'bg-ink-700 text-block border-line', glyph: '✕' },
  completed: { classes: 'bg-ink-700 text-text-dim border-line', glyph: '✓' },
  failed: { classes: 'bg-ink-700 text-text-faint border-line', glyph: '!' },
  queued: { classes: 'bg-ink-700 text-idle border-line', glyph: '○' },
  idle: { classes: 'bg-ink-700 text-idle border-line', glyph: '○' },
}

export function StatusChip({ status }: { status: string }) {
  const style = STATUS_CHIP[status] ?? STATUS_CHIP.queued
  return (
    <span className={cn(CHIP_BASE, style!.classes, 'gap-1')}>
      {/* The glyph is not decoration: it is what keeps the four states
          distinguishable in greyscale and to colour-blind readers. */}
      <span aria-hidden>{style!.glyph}</span>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

export function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn(CHIP_BASE, 'bg-ink-700 text-text-dim border-line', className)}>
      {children}
    </span>
  )
}

// ──────────────────────────────────────────────────────────────────────
// Surfaces
// ──────────────────────────────────────────────────────────────────────

export function Panel({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        'bg-ink-800 border border-line rounded-md shadow-[var(--shadow-panel)]',
        className,
      )}
    >
      {children}
    </section>
  )
}

export function PanelHeader({
  title,
  children,
}: {
  title: ReactNode
  children?: ReactNode
}) {
  return (
    <div className="flex items-center justify-between px-4 h-10 border-b border-line">
      <h2 className="font-ui text-[15px] leading-6 font-semibold text-text">{title}</h2>
      {children}
    </div>
  )
}

export function Card({
  children,
  className,
  attention = false,
  onClick,
}: {
  children: ReactNode
  className?: string
  attention?: boolean
  onClick?: () => void
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-ink-800 rounded-md p-4 border transition-colors duration-100',
        attention
          ? 'border-review/40 shadow-[0_0_0_1px_var(--color-review-subtle)]'
          : 'border-line hover:border-line-strong',
        onClick && 'cursor-pointer',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function StatCard({
  value,
  label,
  onClick,
  tone,
}: {
  value: ReactNode
  label: string
  onClick?: () => void
  tone?: 'spend' | 'block' | 'review' | 'anomaly'
}) {
  const toneClass =
    tone === 'spend'
      ? 'text-spend'
      : tone === 'block'
        ? 'text-block'
        : tone === 'review'
          ? 'text-review'
          : tone === 'anomaly'
            ? 'text-anomaly'
            : 'text-text'

  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-ink-800 border border-line rounded-md px-4 py-3.5',
        onClick && 'cursor-pointer hover:border-line-strong transition-colors duration-100',
      )}
    >
      <div
        className={cn(
          'font-mono text-[28px] leading-8 tabular-nums font-semibold',
          toneClass,
        )}
      >
        {value}
      </div>
      <div className="font-ui text-[11px] leading-4 text-text-faint mt-1">{label}</div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────
// Risk meter
// ──────────────────────────────────────────────────────────────────────

export function RiskMeter({
  score,
  lowConfidence = false,
  sessions,
  width = 'w-28',
}: {
  score: number
  lowConfidence?: boolean
  sessions?: number
  width?: string
}) {
  return (
    <div className="flex items-center gap-2">
      <div className={cn('h-1.5 rounded-xs bg-ink-700 overflow-hidden', width)}>
        <div
          className={cn(
            'h-full rounded-xs transition-[width] duration-300 ease-out',
            // A score built from four sessions must not look as solid as one
            // built from forty. The hatch says so without a tooltip.
            lowConfidence && 'hatched',
          )}
          style={{ width: `${Math.max(2, score)}%`, background: riskColor(score) }}
        />
      </div>
      <span
        className={cn(
          'font-mono text-[12px] tabular-nums font-medium text-text',
          lowConfidence && 'decoration-dotted underline underline-offset-2',
        )}
      >
        {score}
      </span>
      {lowConfidence && sessions !== undefined && (
        <span className="font-ui text-[11px] text-text-faint">
          low confidence — {sessions}/20 sessions
        </span>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────
// Tables
// ──────────────────────────────────────────────────────────────────────

export const table = {
  wrapper: 'bg-ink-800 border border-line rounded-md overflow-hidden',
  head:
    'sticky top-0 z-10 bg-ink-700 border-b border-line font-ui text-[11px] ' +
    'font-medium text-text-faint text-left',
  th: 'px-3 py-2 whitespace-nowrap',
  row: 'border-b border-line/60 hover:bg-ink-700/60 cursor-pointer transition-colors duration-75',
  rowSelected: 'bg-ink-600 border-l-2 border-l-shield',
  cell: 'px-3 py-2 font-mono text-[12px] tabular-nums text-text align-middle',
  cellDense: 'px-3 py-1.5 font-mono text-[12px] tabular-nums text-text align-middle',
}

// ──────────────────────────────────────────────────────────────────────
// Inputs
// ──────────────────────────────────────────────────────────────────────

export const input = {
  text:
    'h-8 w-full px-2.5 rounded-sm bg-ink-900 border border-line font-ui text-[13px] ' +
    'text-text placeholder:text-text-faint focus:outline-none focus:border-shield ' +
    'focus:shadow-[0_0_0_1px_var(--color-shield)] aria-[invalid=true]:border-block ' +
    'aria-[invalid=true]:shadow-[0_0_0_1px_var(--color-block)] disabled:bg-ink-800 ' +
    'disabled:text-text-faint transition-colors duration-100',
  select:
    'h-8 pl-2.5 pr-8 rounded-sm bg-ink-900 border border-line appearance-none ' +
    'font-ui text-[13px] text-text focus:outline-none focus:border-shield',
  label: 'block font-ui text-[11px] font-medium text-text-faint mb-1.5',
  error: 'mt-1 font-ui text-[11px] text-block',
  helper: 'mt-1 font-ui text-[11px] text-text-faint',
  checkbox:
    'h-4 w-4 rounded-xs border border-line bg-ink-900 checked:bg-shield ' +
    'checked:border-shield focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]',
}

export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: string; disabled?: boolean; title?: string }[]
  value: T
  onChange: (value: T) => void
  className?: string
}) {
  return (
    <div
      className={cn(
        'inline-flex items-center gap-0.5 p-0.5 rounded-sm bg-ink-900 border border-line',
        className,
      )}
    >
      {options.map((option) => (
        <button
          key={String(option.value)}
          onClick={() => onChange(option.value)}
          disabled={option.disabled}
          title={option.title}
          className={cn(
            'h-7 px-2.5 rounded-xs font-ui text-[12px] transition-colors duration-100',
            option.value === value
              ? 'bg-ink-600 text-text font-medium'
              : 'text-text-dim hover:text-text',
            option.disabled && 'opacity-40 cursor-not-allowed',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────
// States
// ──────────────────────────────────────────────────────────────────────

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse bg-ink-700 rounded-xs', className)} />
}

export function SkeletonRows({ rows = 8, columns = 5 }: { rows?: number; columns?: number }) {
  const widths = ['w-12', 'w-24', 'w-16', 'w-32', 'w-14', 'w-20']
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <tr key={rowIndex} className="border-b border-line/60">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <td key={columnIndex} className="px-3 py-2">
              <Skeleton className={cn('h-3', widths[columnIndex % widths.length])} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

/**
 * The empty state.
 *
 * Copy rules, from the brief: line one says what would be here, line two says
 * how it gets here, and a button exists only when the reader can cause it. No
 * illustrations, no apologies, no exclamation marks.
 */
export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
}: {
  icon?: React.ComponentType<{ className?: string; strokeWidth?: number }>
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      {Icon && <Icon className="h-6 w-6 text-text-faint" strokeWidth={1.5} />}
      <p className="font-ui text-[13px] font-medium text-text mt-3">{title}</p>
      {hint && (
        <p className="font-ui text-[12px] text-text-faint mt-1 max-w-[42ch]">{hint}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

/**
 * The error state.
 *
 * Names what failed and offers Retry. Never a stack trace, never a raw HTTP
 * code, never an apology -- and whatever had already loaded stays on screen.
 */
export function ErrorState({
  title,
  detail,
  onRetry,
}: {
  title: string
  detail?: string
  onRetry?: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <p className="font-ui text-[13px] font-medium text-text">{title}</p>
      {detail && (
        <p className="font-mono text-[11px] text-text-faint mt-1 max-w-[48ch]">{detail}</p>
      )}
      {onRetry && (
        <Button variant="secondary" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────
// Overlays
// ──────────────────────────────────────────────────────────────────────

/**
 * Drawers are deliberately **not** modal.
 *
 * The simulation keeps running and the canvas stays interactive behind them.
 * Only the fast-forward and create-run dialogs use a backdrop, because those
 * two genuinely take over.
 */
export function Drawer({
  open,
  onClose,
  width = 'w-[420px]',
  children,
}: {
  open: boolean
  onClose: () => void
  width?: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <aside
      role="dialog"
      aria-modal="false"
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      className={cn(
        'fixed right-0 top-14 bottom-0 z-40 bg-ink-800 border-l border-line',
        'shadow-[var(--shadow-drawer)] overflow-y-auto',
        'animate-[drawerin_180ms_cubic-bezier(0.16,1,0.3,1)]',
        width,
      )}
    >
      {children}
    </aside>
  )
}

export function Dialog({
  open,
  onClose,
  title,
  children,
  width = 'w-[440px]',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  width?: string
}) {
  if (!open) return null
  return (
    <>
      <div
        onClick={onClose}
        className="fixed inset-0 z-30 bg-ink-950/70 backdrop-blur-[2px] animate-[fadein_120ms_ease-out]"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={cn(
          'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-50 bg-ink-800',
          'border border-line-strong rounded-lg shadow-[var(--shadow-dialog)] p-5',
          'animate-[dialogin_160ms_ease-out]',
          width,
        )}
      >
        <div className="flex items-start justify-between">
          <h2 className="font-ui text-[15px] leading-6 font-semibold text-text">{title}</h2>
          <button onClick={onClose} className={BUTTON.icon} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </>
  )
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <h3 className="font-ui text-[11px] leading-4 font-medium text-text-faint">{children}</h3>
  )
}
