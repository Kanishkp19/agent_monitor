/**
 * The event pump: Zustand → Phaser.
 *
 * This is the component most likely to be got wrong, so the rules are worth
 * stating plainly:
 *
 * **One subscription, not one per avatar.** Twenty avatars each subscribing to
 * the store, at 200 events/second, is 4,000 React updates a second. There is
 * exactly one subscription in this file, to one slice.
 *
 * **One `requestAnimationFrame` loop, with a budget.** At most twelve events
 * are applied per frame. More than that is invisible anyway -- the eye cannot
 * follow it, and attempting it costs the frame.
 *
 * **The office never fetches.** It drains a queue that the store fills. No
 * `fetch`, no `WebSocket`, no API import anywhere under `src/game/`, and
 * `src/__tests__/office-isolation.test.ts` asserts it.
 */

import type Phaser from 'phaser'

import { EventQueue } from '@/game/systems/EventQueue'
import type { OfficeScene } from '@/game/scenes/OfficeScene'
import { useSim } from '@/stores/simStore'
import { useTelemetry } from '@/stores/telemetryStore'

const EVENTS_PER_FRAME = 12

export interface Bridge {
  stop: () => void
}

export function startBridge(
  game: Phaser.Game,
  onSelect: (employeeId: string) => void,
): Bridge {
  const queue = new EventQueue({ max: 400 })
  let frame = 0
  let lastSpeed = -1

  // One subscription, to one slice. Not the whole event stream.
  const unsubscribeTelemetry = useTelemetry.subscribe((state) => {
    if (state.officeQueue.length === 0) return
    const drained = useTelemetry.getState().drainOfficeQueue(EVENTS_PER_FRAME * 4)
    queue.pushAll(drained)
  })

  // Snapshots are REST-owned and arrive through simStore. The scene rebuilds
  // from them as a hard cut -- see `applySnapshot`.
  const unsubscribeSim = useSim.subscribe((state) => {
    const scene = officeScene(game)
    if (!scene?.ready) return

    if (state.speed !== lastSpeed) {
      lastSpeed = state.speed
      scene.setSpeed(state.speed)
    }
  })

  const applySnapshot = () => {
    const scene = officeScene(game)
    if (!scene?.ready) return
    const avatars = Object.values(useSim.getState().avatars)
    if (avatars.length > 0) scene.applySnapshot(avatars)
  }

  game.events.on('office-ready', applySnapshot)

  const pump = () => {
    const scene = officeScene(game)

    if (scene?.ready) {
      for (const event of queue.drain(EVENTS_PER_FRAME)) {
        scene.applyEvent(event)
      }
    }

    frame = requestAnimationFrame(pump)
  }

  frame = requestAnimationFrame(pump)

  // Selection is the one thing that crosses back out of the canvas.
  game.events.on('avatar-selected', onSelect)

  return {
    stop() {
      cancelAnimationFrame(frame)
      unsubscribeTelemetry()
      unsubscribeSim()
      game.events.off('office-ready', applySnapshot)
      game.events.off('avatar-selected', onSelect)
      queue.clear()
    },
  }
}

function officeScene(game: Phaser.Game): OfficeScene | undefined {
  return game.scene.getScene('OfficeScene') as OfficeScene | undefined
}
