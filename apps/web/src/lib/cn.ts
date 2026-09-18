import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/**
 * Merge class strings, with later Tailwind utilities winning over earlier
 * conflicting ones.
 *
 * Every `className` in this app is built from the token names in
 * `docs/04-UI-UX-BRIEF.md`, never from raw hex.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
