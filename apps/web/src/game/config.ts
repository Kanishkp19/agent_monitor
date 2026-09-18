/**
 * Isometric projection and Phaser configuration.
 *
 * Standard 2:1. The depth rule is the part that bites: depth comes from
 * `(tx + ty)`, never from world `y`. Get it wrong and characters render
 * behind the desks they are sitting at.
 *
 * Nothing in this directory may fetch. The office is a renderer over the
 * telemetry stream -- it reads the Zustand store through `bridge.ts` and has
 * no other input. `src/__tests__/office-isolation.test.ts` asserts it.
 */

import Phaser from 'phaser'

export const TILE_W = 64
export const TILE_H = 32
export const MAP_W = 48
export const MAP_H = 40

/** Tile sprites carry 32px of overhang above the diamond, for walls. */
export const TILE_SPRITE_H = 64

export interface Tile {
  x: number
  y: number
}

export function tileToWorld(tx: number, ty: number): { x: number; y: number } {
  return {
    x: (tx - ty) * (TILE_W / 2),
    y: (tx + ty) * (TILE_H / 2),
  }
}

export function worldToTile(wx: number, wy: number): Tile {
  return {
    x: Math.floor((wx / (TILE_W / 2) + wy / (TILE_H / 2)) / 2),
    y: Math.floor((wy / (TILE_H / 2) - wx / (TILE_W / 2)) / 2),
  }
}

/**
 * The only correct depth rule for 2:1 iso with tall sprites.
 *
 * Layers: 0 floor, 1 furniture, 2 actor, 3 hud.
 */
export function depthFor(tx: number, ty: number, layer = 0): number {
  return (tx + ty) * 10 + layer
}

export const LAYER = {
  FLOOR: 0,
  FURNITURE: 1,
  ACTOR: 2,
  HUD: 3,
} as const

/**
 * Camera zoom is snapped to these values only.
 *
 * Fractional zoom on pixel art produces shimmer -- the sampling grid stops
 * lining up with the source pixels and every edge crawls.
 */
export const ZOOM_STEPS = [0.5, 0.75, 1, 1.5, 2] as const

export function snapZoom(value: number): number {
  return ZOOM_STEPS.reduce((best, step) =>
    Math.abs(step - value) < Math.abs(best - value) ? step : best,
  )
}

export const WORLD_WIDTH = (MAP_W + MAP_H) * (TILE_W / 2)
export const WORLD_HEIGHT = (MAP_W + MAP_H) * (TILE_H / 2)

/** Signal colours, from `docs/04-UI-UX-BRIEF.md` section 2. */
export const COLORS = {
  ink950: 0x080d16,
  ink800: 0x141e2e,
  line: 0x253248,
  text: 0xe6edf7,
  textDim: 0x93a4bd,
  allow: 0x3fcf8e,
  redact: 0xa855f7,
  review: 0xf2a73b,
  block: 0xe5484d,
  anomaly: 0xe668c3,
  idle: 0x64748b,
  shield: 0x3d7bff,
} as const

export const gameConfig: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO, // WebGL preferred, Canvas fallback
  backgroundColor: '#080D16',
  pixelArt: true,
  roundPixels: true,
  antialias: false,
  scale: {
    mode: Phaser.Scale.RESIZE,
    autoCenter: Phaser.Scale.NO_CENTER,
  },
  fps: { target: 60, forceSetTimeOut: false },
  render: { powerPreference: 'low-power' },
}

/**
 * Does the reader want motion?
 *
 * With `prefers-reduced-motion`, the scene teleports instead of tweening,
 * stops the idle bob and makes halos static. Badge and colour changes keep
 * full fidelity -- state is never hidden by an accessibility setting.
 */
export function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}
