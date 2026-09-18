/**
 * One employee on the floor.
 *
 * Holds a sprite, a halo, an FSM state and a tween queue. It does not hold any
 * truth: `risk_score`, `status` and position all come from the store, and a
 * snapshot overwrites whatever the avatar currently believes.
 *
 * Movement is cosmetic. No governed outcome depends on where a character is
 * standing, which is why a failed path can safely teleport.
 */

import Phaser from 'phaser'

import { COLORS, LAYER, TILE_H, depthFor, prefersReducedMotion, tileToWorld } from '@/game/config'
import { animationFor, type AvatarFsmState } from '@/game/systems/AvatarFSM'
import { facingBetween, type Room, findPath } from '@/game/systems/Pathfinder'
import type { Tile } from '@/game/config'

const WALK_SPEED_PX_PER_S = 90
const HALO_RADIUS = 14

const HALO_COLOR: Record<string, number> = {
  working: COLORS.allow,
  waiting: COLORS.review,
  blocked: COLORS.block,
  anomaly: COLORS.anomaly,
}

export class Avatar {
  readonly employeeId: string
  readonly sprite: Phaser.GameObjects.Sprite
  readonly halo: Phaser.GameObjects.Arc

  tile: Tile
  deskTile: Tile
  facing: 'n' | 'e' | 's' | 'w' = 's'
  state: AvatarFsmState = 'idle'
  badge: string = 'none'
  riskScore = 0
  name = ''
  role = ''

  private readonly scene: Phaser.Scene
  private walkTween?: Phaser.Tweens.Tween
  private haloTween?: Phaser.Tweens.Tween
  private holdTimer?: Phaser.Time.TimerEvent

  constructor(
    scene: Phaser.Scene,
    options: {
      employeeId: string
      spriteKey: string
      tile: Tile
      facing: 'n' | 'e' | 's' | 'w'
      name: string
      role: string
    },
  ) {
    this.scene = scene
    this.employeeId = options.employeeId
    this.tile = { ...options.tile }
    this.deskTile = { ...options.tile }
    this.facing = options.facing
    this.name = options.name
    this.role = options.role

    const { x, y } = tileToWorld(this.tile.x, this.tile.y)

    // Drawn first so it sits behind the character rather than over their feet.
    this.halo = scene.add
      .circle(x, y + TILE_H / 4, HALO_RADIUS, COLORS.allow, 0.12)
      .setDepth(depthFor(this.tile.x, this.tile.y, LAYER.ACTOR) - 1)
      .setVisible(false)

    this.sprite = scene.add
      .sprite(x, y, 'characters', `${options.spriteKey}_idle_s_0`)
      .setOrigin(0.5, 0.85)
      .setDepth(depthFor(this.tile.x, this.tile.y, LAYER.ACTOR))
      .setInteractive({ useHandCursor: true })

    this.sprite.setData('employeeId', options.employeeId)
    this.play()
  }

  // ── state ────────────────────────────────────────────────────────

  setState(state: AvatarFsmState, holdMs?: number): void {
    if (this.state === state) return
    this.state = state
    this.play()

    this.holdTimer?.remove()
    if (holdMs) {
      // A blocked avatar returns to idle by itself, so the floor does not
      // accumulate permanent red over a long run.
      this.holdTimer = this.scene.time.delayedCall(holdMs, () => {
        if (this.state === state) {
          this.state = 'idle'
          this.play()
        }
      })
    }
  }

  setBadge(badge: string, riskScore: number): void {
    this.badge = badge
    this.riskScore = riskScore
    this.updateHalo()
  }

  private updateHalo(): void {
    const colour = HALO_COLOR[this.badge]
    this.haloTween?.stop()

    if (!colour || this.badge === 'none') {
      this.halo.setVisible(false)
      return
    }

    this.halo.setVisible(true).setFillStyle(colour, 0.12)

    if (prefersReducedMotion()) {
      this.halo.setAlpha(1)
      return
    }

    // Amber pulses at 1.4s, magenta slower at 2s. Red flashes once and then
    // holds -- a permanently flashing block is noise, not a signal.
    if (this.badge === 'waiting' || this.badge === 'anomaly') {
      this.haloTween = this.scene.tweens.add({
        targets: this.halo,
        alpha: { from: 1, to: 0.35 },
        duration: this.badge === 'waiting' ? 700 : 1000,
        yoyo: true,
        repeat: -1,
      })
    } else {
      this.halo.setAlpha(1)
    }
  }

  private play(): void {
    const key = `${this.spriteKey}_${animationFor(this.state, this.facing)}`
    if (this.scene.anims.exists(key)) {
      this.sprite.play(key, true)
    }
  }

  private get spriteKey(): string {
    return String(this.sprite.frame.name).split('_').slice(0, 2).join('_')
  }

  // ── effects ──────────────────────────────────────────────────────

  shake(): void {
    if (prefersReducedMotion()) return
    const { x } = tileToWorld(this.tile.x, this.tile.y)
    this.scene.tweens.add({
      targets: this.sprite,
      x: { from: x - 3, to: x + 3 },
      duration: 40,
      yoyo: true,
      repeat: 2,
      onComplete: () => this.sprite.setX(x),
    })
  }

  flash(color: number): void {
    this.sprite.setTint(color)
    this.scene.time.delayedCall(220, () => this.sprite.clearTint())
  }

  // ── movement ─────────────────────────────────────────────────────

  /**
   * Walk to a tile. Teleports when no path exists or motion is reduced.
   *
   * A stuck character is far worse than a teleport -- nobody watching notices
   * the cut, and everybody notices someone jammed against a desk.
   */
  walkTo(room: Room, target: Tile, speedMultiplier = 1): void {
    if (this.tile.x === target.x && this.tile.y === target.y) return

    const path = findPath(room, this.tile, target)

    if (path.length === 0 || prefersReducedMotion()) {
      this.teleport(target)
      return
    }

    this.walkTween?.stop()
    this.setState('walking')
    this.followPath(path, speedMultiplier)
  }

  private followPath(path: Tile[], speedMultiplier: number): void {
    const next = path.shift()
    if (!next) {
      this.setState('working')
      return
    }

    this.facing = facingBetween(this.tile, next)
    this.play()

    const from = tileToWorld(this.tile.x, this.tile.y)
    const to = tileToWorld(next.x, next.y)
    const distance = Phaser.Math.Distance.Between(from.x, from.y, to.x, to.y)

    this.walkTween = this.scene.tweens.add({
      targets: [this.sprite, this.halo],
      x: to.x,
      y: (targetObject: unknown) =>
        targetObject === this.halo ? to.y + TILE_H / 4 : to.y,
      duration: (distance / (WALK_SPEED_PX_PER_S * speedMultiplier)) * 1000,
      onComplete: () => {
        this.tile = next
        this.applyDepth()
        this.followPath(path, speedMultiplier)
      },
    })
  }

  teleport(target: Tile): void {
    this.walkTween?.stop()
    this.tile = { ...target }
    const { x, y } = tileToWorld(target.x, target.y)

    if (prefersReducedMotion()) {
      this.sprite.setPosition(x, y)
      this.halo.setPosition(x, y + TILE_H / 4)
      this.applyDepth()
      return
    }

    this.scene.tweens.add({
      targets: this.sprite,
      alpha: 0,
      duration: 75,
      yoyo: true,
      onYoyo: () => {
        this.sprite.setPosition(x, y)
        this.halo.setPosition(x, y + TILE_H / 4)
        this.applyDepth()
      },
    })
  }

  /**
   * Depth is set on placement, never per frame.
   *
   * `scene.children.depthSort()` every frame is one of the three classic
   * mistakes here -- depths only change when someone moves.
   */
  private applyDepth(): void {
    this.sprite.setDepth(depthFor(this.tile.x, this.tile.y, LAYER.ACTOR))
    this.halo.setDepth(depthFor(this.tile.x, this.tile.y, LAYER.ACTOR) - 1)
  }

  get screenPosition(): { x: number; y: number } {
    return { x: this.sprite.x, y: this.sprite.y }
  }

  destroy(): void {
    this.walkTween?.stop()
    this.haloTween?.stop()
    this.holdTimer?.remove()
    this.sprite.destroy()
    this.halo.destroy()
  }
}
