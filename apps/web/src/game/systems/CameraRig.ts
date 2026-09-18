/**
 * Camera: pan, clamp, snap-zoom, tween-to-avatar.
 *
 * Zoom snaps to `ZOOM_STEPS` because fractional zoom on pixel art shimmers --
 * the sampling grid stops lining up with the source pixels and every edge
 * crawls. Panning is clamped to the map so the floor cannot be lost off-screen.
 */

import Phaser from 'phaser'

import { WORLD_HEIGHT, WORLD_WIDTH, ZOOM_STEPS, snapZoom, tileToWorld } from '@/game/config'

const PAN_MARGIN = 400

export class CameraRig {
  private readonly scene: Phaser.Scene
  private readonly camera: Phaser.Cameras.Scene2D.Camera
  private dragging = false
  private lastPointer = { x: 0, y: 0 }

  constructor(scene: Phaser.Scene) {
    this.scene = scene
    this.camera = scene.cameras.main

    this.camera.setBounds(
      -WORLD_WIDTH / 2 - PAN_MARGIN,
      -PAN_MARGIN,
      WORLD_WIDTH + PAN_MARGIN * 2,
      WORLD_HEIGHT + PAN_MARGIN * 2,
    )

    this.attachInput()
    this.fit()
  }

  private attachInput(): void {
    const input = this.scene.input

    input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.dragging = true
      this.lastPointer = { x: pointer.x, y: pointer.y }
    })

    input.on('pointerup', () => {
      this.dragging = false
    })

    input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
      if (!this.dragging) return
      // Divide by zoom so a drag moves the world by the same screen distance
      // at every zoom level -- otherwise panning feels heavy when zoomed in.
      this.camera.scrollX -= (pointer.x - this.lastPointer.x) / this.camera.zoom
      this.camera.scrollY -= (pointer.y - this.lastPointer.y) / this.camera.zoom
      this.lastPointer = { x: pointer.x, y: pointer.y }
    })

    input.on(
      'wheel',
      (_p: Phaser.Input.Pointer, _o: unknown, _dx: number, deltaY: number) => {
        this.step(deltaY > 0 ? -1 : 1)
      },
    )
  }

  /** Move one notch along `ZOOM_STEPS`. Never lands between them. */
  step(direction: 1 | -1): void {
    const current = ZOOM_STEPS.indexOf(snapZoom(this.camera.zoom) as never)
    const next = Math.max(0, Math.min(ZOOM_STEPS.length - 1, current + direction))
    this.camera.setZoom(ZOOM_STEPS[next]!)
  }

  zoomIn(): void {
    this.step(1)
  }

  zoomOut(): void {
    this.step(-1)
  }

  /** Frame the whole floor. The default view on boot. */
  fit(): void {
    this.camera.setZoom(0.5)
    this.camera.centerOn(0, WORLD_HEIGHT / 2)
  }

  /** Pan to an avatar over 300ms. Instant when motion is reduced. */
  panTo(tx: number, ty: number, animate = true): void {
    const { x, y } = tileToWorld(tx, ty)
    if (!animate) {
      this.camera.centerOn(x, y)
      return
    }
    this.camera.pan(x, y, 300, Phaser.Math.Easing.Sine.InOut)
  }

  get zoom(): number {
    return this.camera.zoom
  }

  /**
   * Below 0.6, name plates are unreadable and are replaced by status dots
   * alone. The HUD asks for this rather than deciding on its own.
   */
  get platesVisible(): boolean {
    return this.camera.zoom >= 0.6
  }
}
