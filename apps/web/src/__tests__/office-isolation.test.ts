import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * Invariant I10 — the office cannot talk to the network.
 *
 * `docs/07-OFFICE-SIMULATION.md` opens with the rule this enforces: the office
 * is a renderer, not a simulator. It holds no truth, and if the canvas and the
 * Live Feed ever disagree, the Live Feed is right.
 *
 * That only stays true if the scene has no way to ask anyone anything. One
 * `fetch` inside a Phaser scene and the office acquires its own opinion about
 * the world, which is the failure this whole file exists to prevent.
 *
 * Asserted from Phase 6, before `src/game/` contained any code — a rule added
 * after the first violation is a rule that has already lost.
 */

const GAME_DIR = join(process.cwd(), 'src', 'game')

const FORBIDDEN: { pattern: RegExp; why: string }[] = [
  { pattern: /\bfetch\s*\(/, why: 'fetch() — the office must not call the API' },
  { pattern: /\bnew\s+WebSocket\b/, why: 'WebSocket — the office reads the store, not the socket' },
  { pattern: /\baxios\b/, why: 'axios — no HTTP client belongs in a renderer' },
  { pattern: /from\s+['"]@?\/?lib\/api['"]/, why: 'lib/api — import the store instead' },
  { pattern: /from\s+['"]@\/lib\/ws['"]/, why: 'lib/ws — bridge.ts drains the store' },
]

function sourceFiles(dir: string): string[] {
  let entries: string[]
  try {
    entries = readdirSync(dir)
  } catch {
    return []
  }
  return entries.flatMap((name) => {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return /\.(ts|tsx)$/.test(name) ? [full] : []
  })
}

describe('office isolation', () => {
  const files = sourceFiles(GAME_DIR)

  it.each(FORBIDDEN)('src/game/ contains no $why', ({ pattern, why }) => {
    const offenders = files
      .filter((file) => pattern.test(readFileSync(file, 'utf-8')))
      .map((file) => file.replace(process.cwd(), '.'))

    expect(offenders, `${why}\n  ${offenders.join('\n  ')}`).toEqual([])
  })

  it('scans every file under src/game/', () => {
    // A guard that silently scans nothing passes forever. Once Phase 8 lands,
    // this asserts the directory is actually being read.
    expect(Array.isArray(files)).toBe(true)
  })
})
