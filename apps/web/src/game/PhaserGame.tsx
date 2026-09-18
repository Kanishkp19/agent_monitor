/**
 * The React ⇄ Phaser boundary.
 *
 * React owns mount, unmount and the selection callback. Nothing else crosses
 * in either direction -- no props streaming into the scene, no scene state
 * leaking back out. The office reads the Zustand store through `bridge.ts`,
 * and that is its only input.
 *
 * Keeping this file tiny is the point. Every prop added here is a way for the
 * canvas to acquire an opinion about the world, and the canvas is not allowed
 * to have one.
 */

import { useEffect, useRef } from 'react'
import Phaser from 'phaser'

import { gameConfig } from '@/game/config'
import { startBridge, type Bridge } from '@/game/bridge'
import { BootScene } from '@/game/scenes/BootScene'
import { HudScene } from '@/game/scenes/HudScene'
import { OfficeScene } from '@/game/scenes/OfficeScene'

export function PhaserGame({
  onSelect,
  onError,
}: {
  onSelect: (employeeId: string) => void
  onError?: () => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const gameRef = useRef<Phaser.Game | null>(null)
  const bridgeRef = useRef<Bridge | null>(null)
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  useEffect(() => {
    if (!containerRef.current || gameRef.current) return

    try {
      const game = new Phaser.Game({
        ...gameConfig,
        parent: containerRef.current,
        scene: [BootScene, OfficeScene, HudScene],
      })

      gameRef.current = game

      // The scene emits a selection; React routes it. The scene does not know
      // what a route is.
      game.scene.start('OfficeScene', {
        onSelect: (employeeId: string) => selectRef.current(employeeId),
      })

      bridgeRef.current = startBridge(game, (employeeId) =>
        selectRef.current(employeeId),
      )
    } catch (error) {
      console.error('[office] Phaser failed to start', error)
      onError?.()
    }

    return () => {
      bridgeRef.current?.stop()
      bridgeRef.current = null
      gameRef.current?.destroy(true)
      gameRef.current = null
    }
    // Mount once. `onSelect` is held in a ref so a changing callback does not
    // tear down and rebuild the whole scene.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <div ref={containerRef} className="h-full w-full" />
}
