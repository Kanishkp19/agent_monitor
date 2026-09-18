/**
 * In-room A*, and nothing more.
 *
 * Rooms are separate floating islands with no doors and no corridors, so a
 * path never has to cross between them. That is the whole reason the floor
 * plan looks the way it does -- the hardest part of isometric movement simply
 * does not arise.
 *
 * Grids are at most 20x22, so A* here is a handful of microseconds and needs
 * no optimisation beyond a sorted frontier.
 *
 * If no path exists, the caller teleports with a 150ms fade. Nobody watching
 * a demo notices a teleport; everybody notices a character stuck against a
 * desk forever.
 */

import type { Tile } from '@/game/config'

export interface Room {
  id: string
  origin: [number, number]
  size: [number, number]
  blocked: Set<string>
}

const key = (x: number, y: number) => `${x},${y}`

export function makeRoom(
  id: string,
  origin: [number, number],
  size: [number, number],
  furniture: { at: [number, number] }[],
): Room {
  return {
    id,
    origin,
    size,
    blocked: new Set(furniture.map((f) => key(f.at[0], f.at[1]))),
  }
}

export function contains(room: Room, tile: Tile): boolean {
  return (
    tile.x >= room.origin[0] &&
    tile.x < room.origin[0] + room.size[0] &&
    tile.y >= room.origin[1] &&
    tile.y < room.origin[1] + room.size[1]
  )
}

export function walkable(room: Room, tile: Tile): boolean {
  return contains(room, tile) && !room.blocked.has(key(tile.x, tile.y))
}

/**
 * Four-directional A* on the room's own grid.
 *
 * Returns the path excluding the start tile, or an empty array if there is no
 * route -- which the caller treats as "teleport", not as an error.
 */
export function findPath(room: Room, from: Tile, to: Tile): Tile[] {
  if (from.x === to.x && from.y === to.y) return []
  if (!walkable(room, to)) return []

  const frontier: { tile: Tile; priority: number }[] = [{ tile: from, priority: 0 }]
  const cameFrom = new Map<string, Tile | null>([[key(from.x, from.y), null]])
  const costSoFar = new Map<string, number>([[key(from.x, from.y), 0]])

  while (frontier.length > 0) {
    // A small sorted frontier beats a heap at this grid size, and is far
    // easier to be confident about.
    frontier.sort((a, b) => a.priority - b.priority)
    const current = frontier.shift()!.tile

    if (current.x === to.x && current.y === to.y) break

    for (const next of neighbours(current)) {
      if (!walkable(room, next)) continue

      const nextKey = key(next.x, next.y)
      const newCost = (costSoFar.get(key(current.x, current.y)) ?? 0) + 1

      if (!costSoFar.has(nextKey) || newCost < costSoFar.get(nextKey)!) {
        costSoFar.set(nextKey, newCost)
        frontier.push({ tile: next, priority: newCost + manhattan(next, to) })
        cameFrom.set(nextKey, current)
      }
    }
  }

  const goalKey = key(to.x, to.y)
  if (!cameFrom.has(goalKey)) return []

  const path: Tile[] = []
  let cursor: Tile | null | undefined = to
  while (cursor && !(cursor.x === from.x && cursor.y === from.y)) {
    path.push(cursor)
    cursor = cameFrom.get(key(cursor.x, cursor.y))
  }

  return path.reverse()
}

function neighbours(tile: Tile): Tile[] {
  return [
    { x: tile.x + 1, y: tile.y },
    { x: tile.x - 1, y: tile.y },
    { x: tile.x, y: tile.y + 1 },
    { x: tile.x, y: tile.y - 1 },
  ]
}

function manhattan(a: Tile, b: Tile): number {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
}

/** Which way a character faces when moving between two adjacent tiles. */
export function facingBetween(from: Tile, to: Tile): 'n' | 'e' | 's' | 'w' {
  if (to.x > from.x) return 'e'
  if (to.x < from.x) return 'w'
  if (to.y > from.y) return 's'
  return 'n'
}
