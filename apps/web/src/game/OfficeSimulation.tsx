import { useEffect, useRef } from 'react'
import Phaser from 'phaser'

import { OfficeScene, type OfficeAvatar } from './OfficeScene'
import { useSim } from '@/stores/simStore'

interface OfficeSimulationProps {
  onSelect: (employeeId: string) => void
}

/** Mounts the interactive office while React retains ownership of surrounding UI. */
export function OfficeSimulation({ onSelect }: OfficeSimulationProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const gameRef = useRef<Phaser.Game | null>(null)
  const onSelectRef = useRef(onSelect)
  const avatars = useSim((state) => state.avatars)
  const speed = useSim((state) => state.speed)
  const snapshotRef = useRef({ avatars, speed })

  onSelectRef.current = onSelect
  snapshotRef.current = { avatars, speed }

  useEffect(() => {
    if (!hostRef.current || gameRef.current) return

    const scene = new OfficeScene()
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: hostRef.current,
      scene: [scene],
      backgroundColor: '#080D16',
      pixelArt: true,
      roundPixels: true,
      antialias: false,
      scale: { mode: Phaser.Scale.RESIZE, autoCenter: Phaser.Scale.NO_CENTER },
    })
    const sync = () => scene.sync(snapshotRef.current.avatars as Record<string, OfficeAvatar>, snapshotRef.current.speed)
    const select = (employeeId: string) => onSelectRef.current(employeeId)
    game.events.on('office-ready', sync)
    game.events.on('avatar-selected', select)
    gameRef.current = game

    return () => {
      game.events.off('office-ready', sync)
      game.events.off('avatar-selected', select)
      game.destroy(true)
      gameRef.current = null
    }
  }, [])

  useEffect(() => {
    const scene = gameRef.current?.scene.getScene('OfficeScene') as OfficeScene | undefined
    scene?.sync(avatars as Record<string, OfficeAvatar>, speed)
  }, [avatars, speed])

  return <div ref={hostRef} className="h-full w-full" aria-label="Interactive live office simulation" />
}
