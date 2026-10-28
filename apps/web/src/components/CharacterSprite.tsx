import React from 'react'
import { cn } from '@/lib/cn'

export type CharacterStatus =
  | 'IDLE'
  | 'WORKING'
  | 'WAITING_APPROVAL'
  | 'BLOCKED'
  | 'idle'
  | 'working'
  | 'waiting'
  | 'blocked'
  | 'meeting'
  | 'walking'

export interface CharacterSpriteProps {
  colIndex: number
  rowIndex: number
  status?: CharacterStatus
  scale?: number
  direction?: 's' | 'w' | 'e' | 'n'
  className?: string
  style?: React.CSSProperties
  onClick?: (e: React.MouseEvent<HTMLDivElement>) => void
  'aria-label'?: string
}

export function CharacterSprite({
  colIndex,
  rowIndex,
  status = 'IDLE',
  scale = 1.5,
  direction,
  className,
  style,
  onClick,
  'aria-label': ariaLabel,
}: CharacterSpriteProps) {
  const normStatus = (status ?? 'IDLE').toUpperCase()
  const isWorking = normStatus === 'WORKING'

  // Optional directional row offset (s=0, w=1, e=2, n=3) if using 3x4 block
  const dirOffset =
    direction === 'w' ? 1 : direction === 'e' ? 2 : direction === 'n' ? 3 : 0
  const effectiveRow = rowIndex + dirOffset

  return (
    <div
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      aria-label={ariaLabel}
      className={cn(
        'relative inline-block select-none',
        onClick && 'cursor-pointer focus:outline-none',
        className,
      )}
      style={{
        width: `${32 * scale}px`,
        height: `${32 * scale}px`,
        ...style,
      }}
    >
      <style>{`
        @keyframes character-typing-bob {
          0%, 100% {
            transform: scale(${scale}) translateY(0);
          }
          50% {
            transform: scale(${scale}) translateY(-2px);
          }
        }
      `}</style>
      <div
        className="w-[32px] h-[32px] origin-top-left"
        style={{
          backgroundImage: "url('/characters.png')",
          backgroundRepeat: 'no-repeat',
          backgroundPosition: `calc(-32px * ${colIndex}) calc(-32px * ${effectiveRow})`,
          imageRendering: 'pixelated',
          transform: `scale(${scale})`,
          animation: isWorking ? 'character-typing-bob 0.6s ease-in-out infinite' : undefined,
        }}
      />
    </div>
  )
}

export default CharacterSprite
