import Phaser from 'phaser'

import {
  APPROVAL_POINTS,
  depthFor,
  MEETING_SEATS,
  OFFICE_DESKS,
  OFFICE_ROOMS,
  TILE_HEIGHT,
  TILE_WIDTH,
  tileToWorld,
  type OfficeDesk,
  type OfficeState,
  type TilePosition,
} from './officeLayout'

export interface OfficeAvatar {
  employee_id: string
  name?: string
  fsm: OfficeState
  badge: string
  risk_score: number
}

interface Actor {
  container: Phaser.GameObjects.Container
  halo: Phaser.GameObjects.Ellipse
  label: Phaser.GameObjects.Text
  status: Phaser.GameObjects.Text
  shirt: Phaser.GameObjects.Image
  head: Phaser.GameObjects.Image
  goal: string
  state: OfficeState
  activity?: Phaser.Tweens.Tween
}

const STATUS: Record<OfficeState, { label: string; colour: string }> = {
  idle: { label: '', colour: '#93A4BD' },
  walking: { label: 'MOVING', colour: '#93A4BD' },
  working: { label: 'WORKING', colour: '#3FCF8E' },
  waiting: { label: 'WAITING APPROVAL', colour: '#F2A73B' },
  blocked: { label: 'BLOCKED', colour: '#E5484D' },
  meeting: { label: 'IN MEETING', colour: '#79A7FF' },
}

const SHIRTS = ['blueShirt1.png', 'greenShirt2.png', 'greyShirt3.png', 'redShirt4.png']
const PANTS = ['pantsBlue11.png', 'pantsBrown2.png', 'pantsGrey3.png', 'pantsGreen4.png']
const SHOES = ['blackShoe1.png', 'brownShoe2.png', 'greyShoe3.png', 'blueShoe4.png']
const HAIR = ['blackMan1.png', 'brown1Woman2.png', 'blackWoman3.png', 'brown2Man4.png']

/** A Phaser scene that draws the office from tiles and renders only store-owned state. */
export class OfficeScene extends Phaser.Scene {
  private readonly actors = new Map<string, Actor>()
  private dragStart: TilePosition | null = null
  private latest = new Map<string, OfficeAvatar>()

  constructor() {
    super('OfficeScene')
  }

  preload(): void {
    const root = '/assets/office/kenney'
    this.load.atlasXML('kenney-skin', `${root}/sheet_skin.png`, `${root}/sheet_skin.xml`)
    this.load.atlasXML('kenney-hair', `${root}/sheet_hair.png`, `${root}/sheet_hair.xml`)
    this.load.atlasXML('kenney-shirts', `${root}/sheet_shirts.png`, `${root}/sheet_shirts.xml`)
    this.load.atlasXML('kenney-pants', `${root}/sheet_pants.png`, `${root}/sheet_pants.xml`)
    this.load.atlasXML('kenney-shoes', `${root}/sheet_shoes.png`, `${root}/sheet_shoes.xml`)
  }

  create(): void {
    this.cameras.main.setBackgroundColor('#080D16')
    this.cameras.main.setBounds(-920, 20, 1880, 920)
    this.cameras.main.setZoom(0.48).centerOn(380, 470)
    this.drawOffice()
    this.bindCameraControls()
    this.game.events.emit('office-ready')
  }

  /** Applies a new authoritative snapshot without making network requests. */
  sync(avatars: Record<string, OfficeAvatar>, speed: number): void {
    this.latest = new Map(Object.entries(avatars))
    for (const desk of OFFICE_DESKS) {
      const avatar = this.latest.get(desk.id) ?? this.defaultAvatar(desk)
      const actor = this.actors.get(desk.id) ?? this.createActor(desk)
      this.updateActor(actor, desk, avatar, speed)
    }
  }

  private drawOffice(): void {
    for (const room of OFFICE_ROOMS) this.drawRoom(room)
    for (const desk of OFFICE_DESKS) this.drawDesk(desk)
    this.drawMeetingTable()
    this.drawOfficeDetails()
  }

  private drawRoom(room: (typeof OFFICE_ROOMS)[number]): void {
    const floor = this.add.graphics().setDepth(0)
    const edge = this.add.graphics().setDepth(2).lineStyle(3, 0x242d3d, 1)
    for (let x = room.x; x < room.x + room.width; x += 1) {
      for (let y = room.y; y < room.y + room.height; y += 1) {
        const point = tileToWorld({ x, y })
        floor.fillStyle((x + y) % 2 === 0 ? room.colour : room.colour - 0x080808, 1)
        floor.fillTriangle(point.x, point.y - TILE_HEIGHT / 2, point.x + TILE_WIDTH / 2, point.y, point.x, point.y + TILE_HEIGHT / 2)
        floor.fillTriangle(point.x, point.y - TILE_HEIGHT / 2, point.x, point.y + TILE_HEIGHT / 2, point.x - TILE_WIDTH / 2, point.y)
      }
    }
    const start = tileToWorld({ x: room.x, y: room.y })
    this.add.text(start.x, start.y + TILE_HEIGHT, room.label, {
      fontFamily: 'monospace', fontSize: '14px', fontStyle: 'bold', color: '#E6EDF7', stroke: '#080D16', strokeThickness: 4,
    }).setOrigin(0.5).setDepth(depthFor({ x: room.x, y: room.y }, 8))
    this.drawRoomEdge(edge, room)
  }

  private drawRoomEdge(graphics: Phaser.GameObjects.Graphics, room: (typeof OFFICE_ROOMS)[number]): void {
    const topLeft = tileToWorld({ x: room.x, y: room.y })
    const topRight = tileToWorld({ x: room.x + room.width, y: room.y })
    const bottomLeft = tileToWorld({ x: room.x, y: room.y + room.height })
    const bottomRight = tileToWorld({ x: room.x + room.width, y: room.y + room.height })
    graphics.lineBetween(topLeft.x, topLeft.y, topRight.x, topRight.y)
    graphics.lineBetween(topRight.x, topRight.y, bottomRight.x, bottomRight.y)
    graphics.lineBetween(bottomRight.x, bottomRight.y, bottomLeft.x, bottomLeft.y)
    graphics.lineBetween(bottomLeft.x, bottomLeft.y, topLeft.x, topLeft.y)
  }

  private drawDesk(desk: OfficeDesk): void {
    const at = tileToWorld(desk)
    const graphic = this.add.graphics().setDepth(depthFor(desk, 3))
    graphic.fillStyle(0x5e3f2e, 1)
    graphic.fillTriangle(at.x, at.y - 15, at.x + 30, at.y, at.x, at.y + 15)
    graphic.fillTriangle(at.x, at.y - 15, at.x, at.y + 15, at.x - 30, at.y)
    graphic.fillStyle(0xb7805f, 1).fillRect(at.x - 17, at.y - 13, 34, 8)
    graphic.fillStyle(0x172131, 1).fillRect(at.x - 8, at.y - 26, 16, 13)
    graphic.fillStyle(0x69d3ff, 1).fillRect(at.x - 6, at.y - 24, 12, 8)
    graphic.fillStyle(0x263448, 1).fillCircle(at.x, at.y + 18, 12)
    graphic.lineStyle(2, 0x141923, 1).lineBetween(at.x - 18, at.y + 7, at.x - 12, at.y + 26)
    graphic.lineBetween(at.x + 18, at.y + 7, at.x + 12, at.y + 26)
  }

  private drawMeetingTable(): void {
    const at = tileToWorld({ x: 18, y: 20 })
    const graphic = this.add.graphics().setDepth(depthFor({ x: 18, y: 20 }, 3))
    graphic.fillStyle(0x704a35, 1).fillRoundedRect(at.x - 65, at.y - 25, 130, 50, 8)
    graphic.lineStyle(3, 0xc29170, 1).strokeRoundedRect(at.x - 65, at.y - 25, 130, 50, 8)
    for (const offset of [-50, -25, 0, 25, 50]) {
      graphic.fillStyle(0x303b4d, 1).fillCircle(at.x + offset, at.y - 42, 10)
      graphic.fillStyle(0x303b4d, 1).fillCircle(at.x + offset, at.y + 42, 10)
    }
  }

  private drawOfficeDetails(): void {
    for (const tile of [{ x: 4, y: 5 }, { x: 14, y: 5 }, { x: 29, y: 5 }, { x: 43, y: 21 }]) {
      const at = tileToWorld(tile)
      const plant = this.add.graphics().setDepth(depthFor(tile, 4))
      plant.fillStyle(0x8c5a38, 1).fillRect(at.x - 8, at.y - 10, 16, 14)
      plant.fillStyle(0x3e8e64, 1).fillCircle(at.x, at.y - 19, 13)
      plant.fillStyle(0x5dbd7a, 1).fillCircle(at.x - 8, at.y - 16, 8)
    }
    const coffee = tileToWorld({ x: 42, y: 5 })
    this.add.graphics().setDepth(depthFor({ x: 42, y: 5 }, 4))
      .fillStyle(0xeff4f6, 1).fillRect(coffee.x - 11, coffee.y - 30, 22, 30)
      .fillStyle(0x62b9e8, 1).fillCircle(coffee.x, coffee.y - 22, 8)
  }

  private createActor(desk: OfficeDesk): Actor {
    const at = tileToWorld(desk)
    const index = OFFICE_DESKS.findIndex((candidate) => candidate.id === desk.id)
    const shadow = this.add.ellipse(0, 3, 38, 12, 0x080d16, 0.35)
    const shoes = this.add.image(0, -1, 'kenney-shoes', SHOES[index % SHOES.length]).setScale(0.22)
    const pants = this.add.image(0, -8, 'kenney-pants', PANTS[index % PANTS.length]).setScale(0.21)
    const shirt = this.add.image(0, -23, 'kenney-shirts', SHIRTS[index % SHIRTS.length]).setScale(0.17)
    const head = this.add.image(0, -45, 'kenney-skin', `tint${(index % 8) + 1}_head.png`).setScale(0.16)
    const hair = this.add.image(0, -49, 'kenney-hair', HAIR[index % HAIR.length]).setScale(0.18)
    const halo = this.add.ellipse(0, 2, 42, 16, 0x64748b, 0.2)
    const label = this.add.text(0, -78, desk.name, { fontFamily: 'monospace', fontSize: '10px', color: '#E6EDF7', stroke: '#080D16', strokeThickness: 3 }).setOrigin(0.5)
    const status = this.add.text(0, -65, '', { fontFamily: 'monospace', fontSize: '8px', color: '#93A4BD', stroke: '#080D16', strokeThickness: 3 }).setOrigin(0.5)
    const container = this.add.container(at.x, at.y, [halo, shadow, shoes, pants, shirt, head, hair, label, status])
      .setDepth(depthFor(desk, 5)).setSize(50, 88).setInteractive({ useHandCursor: true })
    container.on('pointerup', () => this.game.events.emit('avatar-selected', desk.id))
    const actor = { container, halo, label, status, shirt, head, goal: '', state: 'idle' as OfficeState }
    this.actors.set(desk.id, actor)
    return actor
  }

  private updateActor(actor: Actor, desk: OfficeDesk, avatar: OfficeAvatar, speed: number): void {
    const state = avatar.fsm === 'walking' ? 'walking' : avatar.fsm
    const display = STATUS[state]
    const isAnomaly = avatar.badge === 'anomaly' || avatar.risk_score >= 70
    actor.label.setText(avatar.name?.split(' ')[0] || desk.name)
    actor.status.setText(isAnomaly ? `RISK ${avatar.risk_score}` : display.label).setColor(isAnomaly ? '#E668C3' : display.colour)
    actor.halo.setFillStyle(Phaser.Display.Color.HexStringToColor(isAnomaly ? '#E668C3' : display.colour).color, state === 'idle' ? 0.12 : 0.35)
    actor.container.setAlpha(speed === 0 ? 0.58 : 1)
    const target = this.targetFor(desk, state)
    const goal = `${target.x},${target.y}:${state}`
    if (actor.goal !== goal) this.walkActor(actor, target, goal, state)
    if (actor.state !== state) this.setActivity(actor, state)
  }

  private targetFor(desk: OfficeDesk, state: OfficeState): TilePosition {
    if (state === 'meeting') return MEETING_SEATS[OFFICE_DESKS.findIndex((entry) => entry.id === desk.id) % MEETING_SEATS.length]!
    if (state === 'waiting') return APPROVAL_POINTS[desk.roomId] ?? desk
    return desk
  }

  private walkActor(actor: Actor, target: TilePosition, goal: string, state: OfficeState): void {
    const at = tileToWorld(target)
    actor.goal = goal
    this.tweens.killTweensOf(actor.container)
    const distance = Phaser.Math.Distance.Between(actor.container.x, actor.container.y, at.x, at.y)
    this.tweens.add({ targets: actor.container, x: at.x, y: at.y, duration: Math.max(160, distance * 3.4), ease: 'Sine.easeInOut', onComplete: () => actor.container.setDepth(depthFor(target, 5)) })
    if (state === 'blocked') this.tweens.add({ targets: actor.container, x: { from: at.x - 4, to: at.x + 4 }, duration: 55, yoyo: true, repeat: 3 })
  }

  private setActivity(actor: Actor, state: OfficeState): void {
    actor.activity?.stop()
    actor.state = state
    if (state === 'working') {
      actor.activity = this.tweens.add({ targets: [actor.shirt, actor.head], y: '+=2', duration: 260, yoyo: true, repeat: -1 })
    } else if (state === 'waiting') {
      actor.activity = this.tweens.add({ targets: actor.halo, alpha: { from: 0.2, to: 0.7 }, duration: 650, yoyo: true, repeat: -1 })
    }
  }

  private bindCameraControls(): void {
    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => { this.dragStart = { x: pointer.x, y: pointer.y } })
    this.input.on('pointerup', () => { this.dragStart = null })
    this.input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
      if (!this.dragStart || !pointer.isDown) return
      this.cameras.main.scrollX -= (pointer.x - this.dragStart.x) / this.cameras.main.zoom
      this.cameras.main.scrollY -= (pointer.y - this.dragStart.y) / this.cameras.main.zoom
      this.dragStart = { x: pointer.x, y: pointer.y }
    })
    this.input.on('wheel', (_pointer: Phaser.Input.Pointer, _objects: unknown, _dx: number, dy: number) => {
      this.cameras.main.setZoom(Phaser.Math.Clamp(this.cameras.main.zoom + (dy < 0 ? 0.12 : -0.12), 0.45, 1.35))
    })
    this.input.keyboard?.on('keydown-LEFT', () => this.panBy(-80, 0))
    this.input.keyboard?.on('keydown-RIGHT', () => this.panBy(80, 0))
    this.input.keyboard?.on('keydown-UP', () => this.panBy(0, -80))
    this.input.keyboard?.on('keydown-DOWN', () => this.panBy(0, 80))
  }

  private panBy(x: number, y: number): void {
    this.cameras.main.scrollX += x / this.cameras.main.zoom
    this.cameras.main.scrollY += y / this.cameras.main.zoom
  }

  private defaultAvatar(desk: OfficeDesk): OfficeAvatar {
    return { employee_id: desk.id, name: desk.name, fsm: desk.roomId === 'meeting' ? 'meeting' : 'idle', badge: 'none', risk_score: 0 }
  }
}
