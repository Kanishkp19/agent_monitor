/**
 * Toasts.
 *
 * Bottom-right, stacked, at most three visible. A 2px left rule carries the
 * variant and nothing else changes -- the colour is the whole signal, so it
 * does not need a coloured background competing with it.
 */

import { Link } from 'react-router-dom'

import { cn } from '@/lib/cn'
import { useUi, type ToastVariant } from '@/stores/uiStore'

const RULE: Record<ToastVariant, string> = {
  success: 'border-l-2 border-l-allow',
  warning: 'border-l-2 border-l-review',
  error: 'border-l-2 border-l-block',
  neutral: 'border-l-2 border-l-line-strong',
}

export function Toaster() {
  const toasts = useUi((s) => s.toasts)
  const dismiss = useUi((s) => s.dismissToast)

  if (toasts.length === 0) return null

  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex w-[360px] flex-col-reverse gap-2"
      role="status"
      aria-live="polite"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            'flex items-start gap-2.5 rounded-md border border-line bg-ink-700 p-3',
            'font-ui text-[13px] text-text shadow-[var(--shadow-raised)]',
            'animate-[toastin_180ms_cubic-bezier(0.16,1,0.3,1)]',
            RULE[toast.variant],
          )}
        >
          <span className="flex-1">{toast.message}</span>
          {toast.action && (
            <Link
              to={toast.action.href}
              onClick={() => dismiss(toast.id)}
              className="shrink-0 font-medium text-shield hover:underline"
            >
              {toast.action.label}
            </Link>
          )}
          <button
            onClick={() => dismiss(toast.id)}
            className="shrink-0 text-text-faint hover:text-text"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
