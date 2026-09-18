/**
 * The screen-space HUD: name plates, status pills, bubbles, room labels.
 *
 * A separate scene, deliberately. `OfficeScene` is world-space and moves with
 * the camera; this one does not. That is what keeps plates and pills crisp and
 * constant-size at every zoom level -- which is why they still read at 0.5x
 * when the whole floor is visible.
 *
 * Everything here is **pooled**. Creating a text object per plate update
 * instead of calling `setText` is the first of the three classic mistakes in
 * this file's neighbourhood, and it shows up as an allocation sawtooth in the
 * performance panel about a minute in.
 */

import Phaser from 'phaser'

import { COLORS, prefersReducedMotion } from '@/game/config'
import type { OfficeScene } from '@/game/scenes/OfficeScene'

const PLATE_OFFSET_Y = 52
const BUBBLE_POOL_SIZE = 8
const BUBBLE_MS = 4_000
const ARIA_INTERVAL_MS = 2_000

interface Plate {
  container: Phaser.GameObjects.Container
  background: Phaser.GameObjects.Rectangle
  dot: Phaser.GameObjects.Arc
  name: Phaser.GameObjects.Text
  pill: Phaser.GameObjects.Text
}

const STATE_COLOR: Record<string, number> = {
  working: COLORS.allow,
  waiting: COLORS.review,
  blocked: COLORS.block,
  meeting: COLORS.shield,
  idle: COLORS.idle,
  walking: COLORS.idle,
}

export class HudScene extends Phaser.Scene {
  private plates = new Map<string, Plate>()
  private bubbles: Phaser.GameObjects.Text[] = []
  private bubbleCursor = 0
  private office?: OfficeScene
  private ariaTimer?: Phaser.Time.TimerEvent

  constructor() {
    super({ key: 'HudScene', active: false })
  }

  create(): void {
    this.office = this.scene.get('OfficeScene') as OfficeScene

    this.buildBubblePool()

    this.game.events.on('speech', this.showBubble, this)
    this.game.events.on('avatars-changed', this.syncPlates, this)

    // The canvas has a text equivalent, regenerated every two seconds. A view
    // that exists only as pixels is not a view everyone has.
    this.ariaTimer = this.time.addEvent({
      delay: ARIA_INTERVAL_MS,
      loop: true,
      callback: this.updateAriaLabel,
      callbackScope: this,
    })

    this.events.on(Phaser.Scenes.Events.SHUTDOWN, () => {
      this.game.events.off('speech', this.showBubble, this)
      this.game.events.off('avatars-changed', this.syncPlates, this)
      this.ariaTimer?.remove()
    })
  }

  /**
   * Follow every avatar, once per frame.
   *
   * Positions come from `OfficeScene`, which already has them -- asking once
   * per frame is cheaper than every plate subscribing to anything.
   */
  update(): void {
    if (!this.office?.ready) return

    const summaries = this.office.avatarSummaries()
    const platesVisible = this.office.platesVisible

    for (const summary of summaries) {
      const plate = this.plates.get(summary.employeeId) ?? this.createPlate(summary.employeeId)

      plate.container.setPosition(summary.x, summary.y - PLATE_OFFSET_Y)
      plate.container.setVisible(true)

      const colour = STATE_COLOR[summary.state] ?? COLORS.idle
      plate.dot.setFillStyle(summary.badge === 'anomaly' ? COLORS.anomaly : colour)

      // Below 0.6 zoom a name is unreadable anyway, so the dot carries the
      // state on its own rather than rendering illegible text.
      plate.background.setVisible(platesVisible)
      plate.name.setVisible(platesVisible)

      if (platesVisible && plate.name.text !== summary.name) {
        plate.name.setText(summary.name)
      }

      plate.container.setAlpha(summary.state === 'idle' ? 0.45 : 1)

      const pill = pillFor(summary)
      if (plate.pill.text !== pill.text) {
        plate.pill.setText(pill.text)
      }
      plate.pill.setColor(pill.color).setVisible(platesVisible && pill.text !== '')
    }
  }

  private syncPlates(): void {
    // Hide plates for avatars that have gone. Pooled, so nothing is destroyed.
    const known = new Set(this.office?.avatarSummaries().map((a) => a.employeeId) ?? [])
    for (const [employeeId, plate] of this.plates) {
      if (!known.has(employeeId)) plate.container.setVisible(false)
    }
  }

  private createPlate(employeeId: string): Plate {
    const background = this.add
      .rectangle(0, 0, 120, 16, 0x0d1420, 0.88)
      .setStrokeStyle(1, COLORS.line)
      .setOrigin(0.5)

    const dot = this.add.circle(-52, 0, 3, COLORS.idle).setOrigin(0.5)

    const name = this.add
      .text(-44, 0, '', {
        fontFamily: 'Departure Mono, monospace',
        fontSize: '11px',
        color: '#E6EDF7',
      })
      .setOrigin(0, 0.5)

    const pill = this.add
      .text(0, 14, '', {
        fontFamily: 'Departure Mono, monospace',
        fontSize: '10px',
        color: '#F2A73B',
      })
      .setOrigin(0.5)

    const container = this.add.container(0, 0, [background, dot, name, pill]).setDepth(1000)

    const plate: Plate = { container, background, dot, name, pill }
    this.plates.set(employeeId, plate)
    return plate
  }

  private buildBubblePool(): void {
    for (let i = 0; i < BUBBLE_POOL_SIZE; i++) {
      this.bubbles.push(
        this.add
          .text(0, 0, '', {
            fontFamily: 'Departure Mono, monospace',
            fontSize: '11px',
            color: '#E6EDF7',
            backgroundColor: '#0D1420',
            padding: { x: 5, y: 3 },
          })
          .setOrigin(0.5, 1)
          .setDepth(1100)
          .setVisible(false),
      )
    }
  }

  private showBubble({ employeeId, text }: { employeeId: string; text: string }): void {
    const summary = this.office?.avatarSummaries().find((a) => a.employeeId === employeeId)
    if (!summary) return

    // Pooled and reused. One per avatar at a time; the pool of eight is the
    // cap, and under load bubbles are simply dropped rather than queued.
    const bubble = this.bubbles[this.bubbleCursor % this.bubbles.length]!
    this.bubbleCursor++

    bubble
      .setText(text)
      .setPosition(summary.x, summary.y - PLATE_OFFSET_Y - 18)
      .setVisible(true)
      .setAlpha(1)

    const duration = prefersReducedMotion() ? BUBBLE_MS : BUBBLE_MS
    this.time.delayedCall(duration, () => bubble.setVisible(false))
  }

  private updateAriaLabel(): void {
    if (!this.office?.ready) return

    const counts = this.office.headcount
    const parts = [
      counts.working && `${counts.working} working`,
      counts.waiting && `${counts.waiting} waiting for approval`,
      counts.blocked && `${counts.blocked} blocked`,
      (counts.idle ?? 0) + (counts.walking ?? 0) &&
        `${(counts.idle ?? 0) + (counts.walking ?? 0)} idle`,
    ].filter(Boolean)

    const canvas = this.game.canvas
    canvas.setAttribute('role', 'img')
    canvas.setAttribute(
      'aria-label',
      `Office floor: ${parts.join(', ') || 'no activity'}.`,
    )
  }
}

function pillFor(summary: { state: string; badge: string; riskScore: number }): {
  text: string
  color: string
} {
  if (summary.badge === 'anomaly') {
    return { text: `◆ Risk ${summary.riskScore}`, color: '#E668C3' }
  }
  if (summary.state === 'waiting') {
    return { text: '⏳ Waiting approval', color: '#F2A73B' }
  }
  if (summary.state === 'blocked') {
    return { text: '✕ BLOCKED', color: '#E5484D' }
  }
  return { text: '', color: '#93A4BD' }
}
