/**
 * A bounded, coalescing queue between the store and the scene.
 *
 * Two rules, both from `docs/07-OFFICE-SIMULATION.md` section 8:
 *
 * **Bounded.** 400 events, oldest dropped. At 10x the server is already
 * batching, but a tab that was backgrounded for a minute must not come back to
 * a ten-thousand-event backlog it tries to animate.
 *
 * **Coalescing, except for blocks.** If two events for the same employee land
 * in one drain, only the last is applied -- *unless* one of them is a block.
 * A block that flickers past invisibly defeats the purpose of the whole view,
 * so it always wins and always animates.
 */

import type { EventEnvelope } from '@/types/generated'

export class EventQueue {
  private items: EventEnvelope[] = []
  private readonly max: number

  constructor({ max = 400 }: { max?: number } = {}) {
    this.max = max
  }

  get size(): number {
    return this.items.length
  }

  pushAll(events: EventEnvelope[]): void {
    if (events.length === 0) return
    this.items.push(...events)
    if (this.items.length > this.max) {
      this.items = this.items.slice(-this.max)
    }
  }

  /**
   * Take up to `budget` events, coalesced per employee.
   *
   * The budget exists because more than about a dozen visual changes in one
   * frame is invisible anyway -- the eye cannot follow them, and attempting
   * them costs the frame.
   */
  drain(budget: number): EventEnvelope[] {
    if (this.items.length === 0) return []

    const taken = this.items.splice(0, budget)
    const latestPerEmployee = new Map<string, EventEnvelope>()
    const blocks: EventEnvelope[] = []

    for (const event of taken) {
      const employeeId = event.detail.employee_id
      if (!employeeId) continue

      if (isBlock(event)) {
        blocks.push(event)
        continue
      }
      latestPerEmployee.set(employeeId, event)
    }

    // Blocks first, so a subsequent state change for the same person lands on
    // top of a block that was definitely seen.
    return [...blocks, ...latestPerEmployee.values()]
  }

  clear(): void {
    this.items = []
  }
}

function isBlock(event: EventEnvelope): boolean {
  const payload = event.detail.payload as Record<string, unknown>
  return (
    payload.decision === 'block' ||
    event.detail_type === 'action.blocked' ||
    (event.detail_type === 'approval.decided' &&
      !String(payload.status ?? '').startsWith('approved'))
  )
}
