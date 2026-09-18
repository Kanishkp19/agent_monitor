/**
 * The world-space scene: floor, furniture, avatars, camera, input.
 *
 * **The office is a renderer, not a simulator.** It holds no truth. Closing the
 * tab changes nothing. It cannot start, stop, approve, block or schedule
 * anything -- it can only show what already happened. If it and the Live Feed
 * ever disagree, the feed is right and this resnapshots.
 *
 * Two performance decisions carry the frame budget:
 *
 * - **The floor is flattened into one RenderTexture.** Roughly 1,800 tiles
 *   collapse to a single draw call, painted once at boot and never per frame.
 * - **Furniture stays as individual sprites** (about 90), because avatars must
 *   be able to render both in front of and behind them.
 */

import Phaser from 'phaser'

import {
  COLORS,
  LAYER,
  TILE_H,
  TILE_W,
  WORLD_HEIGHT,
  WORLD_WIDTH,
  depthFor,
  tileToWorld,
} from '@/game/config'
import { Avatar } from '@/game/entities/Avatar'
import { CameraRig } from '@/game/systems/CameraRig'
import { transitionFor } from '@/game/systems/AvatarFSM'
import { makeRoom, type Room } from '@/game/systems/Pathfinder'
import type { AvatarState } from '@/lib/api'
import type { EventEnvelope } from '@/types/generated'

interface RoomSpec {
  id: string
  label: string
  origin: [number, number]
  size: [number, number]
  floorTile: string
  walls?: { back: string; left: string }
  labelAnchor: [number, number]
  furniture: { type: string; at: [number, number] }[]
  desks: { slot: string; at: [number, number]; facing: string }[]
}

export class OfficeScene extends Phaser.Scene {
  ready = false

  private avatars = new Map<string, Avatar>()
  private rooms = new Map<string, Room>()
  private roomOf = new Map<string, string>()
  private camera!: CameraRig
  private onSelect?: (employeeId: string) => void
  private speedMultiplier = 1

  constructor() {
    super('OfficeScene')
  }

  init(data: { onSelect?: (employeeId: string) => void }): void {
    this.onSelect = data.onSelect
  }

  create(): void {
    const map = this.cache.json.get('office-map') as { rooms: RoomSpec[] } | undefined
    const rooms = map?.rooms ?? []

    this.paintFloor(rooms)
    this.placeFurniture(rooms)
    this.registerRooms(rooms)

    this.camera = new CameraRig(this)
    this.attachInput()

    this.ready = true
    this.game.events.emit('office-ready')
  }

  // ── static world, painted once ───────────────────────────────────

  private paintFloor(rooms: RoomSpec[]): void {
    const texture = this.add
      .renderTexture(-WORLD_WIDTH / 2, 0, WORLD_WIDTH, WORLD_HEIGHT)
      .setOrigin(0)
      .setDepth(LAYER.FLOOR)

    const draw = (tx: number, ty: number, tile: string) => {
      const { x, y } = tileToWorld(tx, ty)
      const frame = this.textureFor(tile)
      if (!frame) return
      texture.draw(frame.key, frame.frame, x + WORLD_WIDTH / 2 - TILE_W / 2, y - TILE_H / 2)
    }

    for (const room of rooms) {
      const [ox, oy] = room.origin
      const [w, h] = room.size

      // Walls first, so the floor overlaps their base rather than the reverse.
      if (room.walls) {
        for (let i = 0; i < w; i++) draw(ox + i, oy - 1, room.walls.back)
        for (let j = 0; j < h; j++) draw(ox - 1, oy + j, room.walls.left)
      }

      for (let i = 0; i < w; i++) {
        for (let j = 0; j < h; j++) {
          draw(ox + i, oy + j, room.floorTile)
        }
      }
    }
  }

  private placeFurniture(rooms: RoomSpec[]): void {
    for (const room of rooms) {
      for (const item of room.furniture) {
        const frame = this.textureFor(item.type)
        if (!frame) continue

        const { x, y } = tileToWorld(item.at[0], item.at[1])
        this.add
          .image(x, y, frame.key, frame.frame)
          .setOrigin(0.5, 1)
          .setDepth(depthFor(item.at[0], item.at[1], LAYER.FURNITURE))
      }
    }
  }

  private registerRooms(rooms: RoomSpec[]): void {
    for (const room of rooms) {
      this.rooms.set(room.id, makeRoom(room.id, room.origin, room.size, room.furniture))
    }
  }

  private textureFor(name: string): { key: string; frame?: string } | null {
    if (this.textures.exists('tiles') && this.textures.getFrame('tiles', name)) {
      return { key: 'tiles', frame: name }
    }
    if (this.textures.exists(`tile_${name}`)) {
      return { key: `tile_${name}` }
    }
    return null
  }

  private attachInput(): void {
    this.input.on(
      'gameobjectdown',
      (_pointer: Phaser.Input.Pointer, object: Phaser.GameObjects.GameObject) => {
        const employeeId = object.getData('employeeId') as string | undefined
        if (!employeeId) return

        this.onSelect?.(employeeId)

        const avatar = this.avatars.get(employeeId)
        if (avatar) this.camera.panTo(avatar.tile.x, avatar.tile.y)
      },
    )
  }

  // ── the only way office visuals change ───────────────────────────

  /**
   * Apply one event.
   *
   * Events whose employee the scene does not know are silently discarded --
   * that happens legitimately after a run switch, and throwing would take down
   * the pump for a condition that resolves itself.
   */
  applyEvent(event: EventEnvelope): void {
    const employeeId = event.detail.employee_id
    if (!employeeId) return

    const avatar = this.avatars.get(employeeId)
    if (!avatar) return

    const transition = transitionFor(avatar.state, event)
    if (!transition) return

    avatar.setState(transition.state, transition.holdMs)

    switch (transition.effect) {
      case 'shake':
        avatar.shake()
        break
      case 'flash-green':
        avatar.flash(COLORS.allow)
        break
      case 'spark-redact':
        avatar.flash(COLORS.redact)
        break
      case 'bell':
        this.game.events.emit('manager-bell', employeeId)
        break
    }

    if (transition.bubble) {
      this.game.events.emit('speech', { employeeId, text: transition.bubble })
    }

    const payload = event.detail.payload as Record<string, unknown>
    if (event.detail_type === 'risk.updated') {
      const score = Number(payload.score ?? avatar.riskScore)
      avatar.setBadge(score >= 70 ? 'anomaly' : badgeForState(avatar.state), score)
    } else {
      avatar.setBadge(
        avatar.riskScore >= 70 ? 'anomaly' : badgeForState(transition.state),
        avatar.riskScore,
      )
    }
  }

  /**
   * Rebuild from a snapshot.
   *
   * A hard cut with no tweens, deliberately: an animated catch-up would be a
   * lie about what happened and when.
   */
  applySnapshot(avatars: AvatarState[]): void {
    const seen = new Set<string>()

    for (const state of avatars) {
      seen.add(state.employee_id)
      const existing = this.avatars.get(state.employee_id)

      if (existing) {
        existing.teleport({ x: state.tile.x, y: state.tile.y })
        existing.setState(state.fsm)
        existing.setBadge(state.badge, state.risk_score)
        continue
      }

      this.avatars.set(
        state.employee_id,
        this.spawn(state),
      )
    }

    // Anyone absent from the snapshot has left the run.
    for (const [employeeId, avatar] of this.avatars) {
      if (!seen.has(employeeId)) {
        avatar.destroy()
        this.avatars.delete(employeeId)
      }
    }

    this.game.events.emit('avatars-changed', this.avatarSummaries())
  }

  private spawn(state: AvatarState): Avatar {
    const avatar = new Avatar(this, {
      employeeId: state.employee_id,
      spriteKey: state.sprite_key,
      tile: { x: state.tile.x, y: state.tile.y },
      facing: state.facing,
      name: state.name,
      role: state.role,
    })
    avatar.setState(state.fsm)
    avatar.setBadge(state.badge, state.risk_score)

    const room = this.roomContaining(state.tile.x, state.tile.y)
    if (room) this.roomOf.set(state.employee_id, room)

    return avatar
  }

  private roomContaining(tx: number, ty: number): string | undefined {
    for (const [id, room] of this.rooms) {
      const [ox, oy] = room.origin
      const [w, h] = room.size
      if (tx >= ox && tx < ox + w && ty >= oy && ty < oy + h) return id
    }
    return undefined
  }

  // ── speed ────────────────────────────────────────────────────────

  /**
   * At 10x, walking doubles rather than 10x-ing.
   *
   * Ten times walk speed looks like a bug, not like speed. Badge transitions
   * keep their full duration at every speed, because they are the information.
   */
  setSpeed(speed: number): void {
    this.speedMultiplier = speed >= 10 ? 2 : 1
    if (speed === 0) {
      this.anims.pauseAll()
      this.cameras.main.setAlpha(0.6)
    } else {
      this.anims.resumeAll()
      this.cameras.main.setAlpha(1)
    }
  }

  zoomIn(): void {
    this.camera.zoomIn()
  }

  zoomOut(): void {
    this.camera.zoomOut()
  }

  fitView(): void {
    this.camera.fit()
  }

  get zoom(): number {
    return this.camera.zoom
  }

  get platesVisible(): boolean {
    return this.camera.platesVisible
  }

  /** Screen positions for the HUD, computed once per frame by HudScene. */
  avatarSummaries(): {
    employeeId: string
    name: string
    role: string
    state: string
    badge: string
    riskScore: number
    x: number
    y: number
  }[] {
    const camera = this.cameras.main
    return [...this.avatars.values()].map((avatar) => ({
      employeeId: avatar.employeeId,
      name: avatar.name,
      role: avatar.role,
      state: avatar.state,
      badge: avatar.badge,
      riskScore: avatar.riskScore,
      x: (avatar.sprite.x - camera.scrollX) * camera.zoom,
      y: (avatar.sprite.y - camera.scrollY) * camera.zoom,
    }))
  }

  get headcount(): Record<string, number> {
    const counts: Record<string, number> = {}
    for (const avatar of this.avatars.values()) {
      counts[avatar.state] = (counts[avatar.state] ?? 0) + 1
    }
    return counts
  }
}

function badgeForState(state: string): string {
  switch (state) {
    case 'working':
      return 'working'
    case 'waiting':
      return 'waiting'
    case 'blocked':
      return 'blocked'
    default:
      return 'none'
  }
}
