/**
 * Asset loading, animation registration, and the handoff to OfficeScene.
 *
 * If the atlases are missing, this generates flat-colour textures at runtime
 * rather than failing. That keeps the office renderable on a clean clone where
 * nobody has run `make_placeholder_atlas.py` yet -- a blank canvas reads as a
 * bug, and a crude floor reads as a floor.
 */

import Phaser from 'phaser'

import { COLORS, TILE_H, TILE_W } from '@/game/config'

const FACINGS = ['n', 'e', 's', 'w'] as const
const CHARACTER_COUNT = 8

const ANIMATION_SPEC = {
  idle: { frames: 2, rate: 2 },
  walk: { frames: 4, rate: 8 },
  type: { frames: 2, rate: 6 },
} as const

export class BootScene extends Phaser.Scene {
  constructor() {
    super('BootScene')
  }

  preload(): void {
    const bar = this.showLoadingBar()

    this.load.atlas(
      'tiles',
      'assets/office/tileset.png',
      'assets/office/tileset.json',
    )
    this.load.atlas(
      'characters',
      'assets/office/characters.png',
      'assets/office/characters.json',
    )
    this.load.json('office-map', 'assets/office/office-map.json')

    this.load.on('progress', (value: number) => bar.setScale(value, 1))

    // A missing atlas is not fatal. The scene still needs to render.
    this.load.on('loaderror', (file: Phaser.Loader.File) => {
      console.warn(`[office] missing asset: ${file.key} — using generated placeholders`)
    })
  }

  create(): void {
    if (!this.textures.exists('tiles')) this.generateTiles()
    if (!this.textures.exists('characters')) this.generateCharacters()

    this.registerAnimations()
    this.scene.start('OfficeScene')
    this.scene.launch('HudScene')
  }

  private showLoadingBar(): Phaser.GameObjects.Rectangle {
    const { width, height } = this.scale
    this.add
      .text(width / 2, height / 2 - 24, 'Loading the floor…', {
        fontFamily: 'Departure Mono, monospace',
        fontSize: '13px',
        color: '#93A4BD',
      })
      .setOrigin(0.5)

    return this.add
      .rectangle(width / 2 - 100, height / 2, 200, 3, COLORS.shield)
      .setOrigin(0, 0.5)
      .setScale(0, 1)
  }

  /**
   * Register every animation once, up front.
   *
   * 8 characters x 3 animations x 4 facings. Doing this at boot rather than
   * lazily means `sprite.play()` is a lookup, never an allocation.
   */
  private registerAnimations(): void {
    for (let character = 0; character < CHARACTER_COUNT; character++) {
      const prefix = `char_${String(character).padStart(2, '0')}`

      for (const [animation, spec] of Object.entries(ANIMATION_SPEC)) {
        for (const facing of FACINGS) {
          const key = `${prefix}_${animation}_${facing}`
          if (this.anims.exists(key)) continue

          const frames = Array.from({ length: spec.frames }, (_, index) => ({
            key: 'characters',
            frame: `${prefix}_${animation}_${facing}_${index}`,
          })).filter((frame) => this.textures.getFrame('characters', frame.frame))

          if (frames.length === 0) continue

          this.anims.create({
            key,
            frames,
            frameRate: spec.rate,
            repeat: -1,
          })
        }
      }
    }
  }

  // ── runtime fallbacks ────────────────────────────────────────────

  private generateTiles(): void {
    const graphics = this.make.graphics({ x: 0, y: 0 }, false)
    const tiles: Record<string, number> = {
      floor_grey: 0x1c293c,
      floor_wood: 0x2a241c,
      floor_carpet_red: 0x2e1e24,
      brick_nw: 0x253248,
      brick_ne: 0x1e293c,
      desk_e: 0x3a3026,
      chair_e: 0x27374e,
      monitor: 0x0d1420,
      partition: 0x33455f,
      plant_tall: 0x3fcf8e,
      plant_small: 0x3fcf8e,
      water_cooler: 0x93a4bd,
      coffee: 0xe8c468,
      whiteboard: 0xe6edf7,
      server_rack: 0x1c293c,
      printer: 0x5c6e89,
      meeting_table: 0x3a3026,
      bookshelf: 0x3a3026,
      chair_n: 0x27374e,
      chair_s: 0x27374e,
    }

    Object.entries(tiles).forEach(([name, colour]) => {
      graphics.clear()
      graphics.fillStyle(colour, 1)
      graphics.beginPath()
      graphics.moveTo(TILE_W / 2, 0)
      graphics.lineTo(TILE_W, TILE_H / 2)
      graphics.lineTo(TILE_W / 2, TILE_H)
      graphics.lineTo(0, TILE_H / 2)
      graphics.closePath()
      graphics.fillPath()
      graphics.generateTexture(`tile_${name}`, TILE_W, TILE_H)
    })

    graphics.destroy()
  }

  private generateCharacters(): void {
    const shirts = [
      0x3d7bff, 0x3fcf8e, 0xf2a73b, 0xa855f7, 0xe5484d, 0xe668c3, 0x93a4bd, 0xe8c468,
    ]

    shirts.forEach((shirt, index) => {
      const graphics = this.make.graphics({ x: 0, y: 0 }, false)
      graphics.fillStyle(0xc8a07a, 1)
      graphics.fillRect(12, 8, 8, 9)
      graphics.fillStyle(shirt, 1)
      graphics.fillRect(10, 17, 12, 19)
      graphics.fillStyle(0x1c293c, 1)
      graphics.fillRect(11, 36, 4, 10)
      graphics.fillRect(17, 36, 4, 10)
      graphics.generateTexture(`char_${String(index).padStart(2, '0')}_fallback`, 32, 48)
      graphics.destroy()
    })
  }
}
