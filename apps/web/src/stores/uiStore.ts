/**
 * Client-only view state: role filter, drawers, toasts.
 *
 * Nothing here is authoritative about anything. The role selector is a view
 * filter (`viewAs`), not a permission -- v1 has no auth, and modelling it as
 * one in the store would make the eventual real thing harder to add, not
 * easier.
 */

import { create } from 'zustand'

export type ViewAs = 'security_admin' | 'manager' | 'ceo' | 'engineer'
export type ToastVariant = 'success' | 'warning' | 'error' | 'neutral'

export interface Toast {
  id: string
  variant: ToastVariant
  message: string
  action?: { label: string; href: string }
  /** `null` means the reader dismisses it. Errors do not disappear on their own. */
  ttlMs: number | null
}

interface UiState {
  viewAs: ViewAs
  selectedEmployee: string | null
  selectedTask: string | null
  expandedRow: number | null
  toasts: Toast[]
  simpleOfficeView: boolean
  /** The office route shows a fixed 340px SYSTEM LOG rail; drawers must not cover it. */
  systemLogRail: boolean

  setViewAs: (role: ViewAs) => void
  setSystemLogRail: (on: boolean) => void
  selectEmployee: (id: string | null) => void
  selectTask: (id: string | null) => void
  expandRow: (seq: number | null) => void
  toggleSimpleView: () => void
  toast: (variant: ToastVariant, message: string, options?: Partial<Toast>) => void
  dismissToast: (id: string) => void
}

const DEFAULT_TTL: Record<ToastVariant, number | null> = {
  success: 3_000,
  neutral: 3_000,
  warning: 6_000,
  // An error nobody saw is an error that did not get reported.
  error: null,
}

const MAX_VISIBLE_TOASTS = 3

export const useUi = create<UiState>((set, get) => ({
  viewAs: (import.meta.env.VITE_DEFAULT_ROLE as ViewAs) ?? 'security_admin',
  selectedEmployee: null,
  selectedTask: null,
  expandedRow: null,
  toasts: [],
  simpleOfficeView: false,
  systemLogRail: false,

  setViewAs: (viewAs) => set({ viewAs }),
  setSystemLogRail: (systemLogRail) => set({ systemLogRail }),
  selectEmployee: (selectedEmployee) => set({ selectedEmployee }),
  selectTask: (selectedTask) => set({ selectedTask }),
  expandRow: (expandedRow) => set({ expandedRow }),
  toggleSimpleView: () => set({ simpleOfficeView: !get().simpleOfficeView }),

  toast: (variant, message, options) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
    const entry: Toast = {
      id,
      variant,
      message,
      ttlMs: options?.ttlMs ?? DEFAULT_TTL[variant],
      ...(options?.action ? { action: options.action } : {}),
    }

    set({ toasts: [...get().toasts, entry].slice(-MAX_VISIBLE_TOASTS) })

    if (entry.ttlMs !== null) {
      window.setTimeout(() => get().dismissToast(id), entry.ttlMs)
    }
  },

  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}))
