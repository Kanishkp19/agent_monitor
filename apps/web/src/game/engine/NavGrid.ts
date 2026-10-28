/**
 * Tile-based navigation: walkability grid + A* with sight smoothing.
 *
 * Built once per room from Furniture footprints (data-driven, not
 * hardcoded): walls are the grid border, furniture rects block their
 * tiles. People never clip through a desk because the desks are solid
 * in the grid — the same data that the art was painted from.
 *
 * Coordinates are room-LOCAL tiles, integers 0..w-1 / 0..h-1. Non-integer
 * positions are snapped to the nearest walkable tile when pathing starts.
 *
 * The 4-neighbor grid produces L-shaped routes; `smooth` removes zig-zag
 * collinear steps so motion reads as confident striding instead of
 * staircase wiggling. Diagonal corner-cutting is deliberately not
 * allowed — people turn through room centers, not through desk corners.
 */

export interface NavGrid {
  w: number
  h: number
  /** blocked[y * w + x] — true means solid. */
  blocked: Uint8Array
}

export function buildNavGrid(w: number, h: number, rects: [number, number, number, number][]): NavGrid {
  const blocked = new Uint8Array(w * h)
  for (const [rx, ry, rw, rd] of rects) {
    const x0 = Math.max(0, Math.floor(rx))
    const y0 = Math.max(0, Math.floor(ry))
    const x1 = Math.min(w - 1, Math.ceil(rx + rw) - 1)
    const y1 = Math.min(h - 1, Math.ceil(ry + rd) - 1)
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        blocked[y * w + x] = 1
      }
    }
  }
  return { w, h, blocked }
}

export function isBlocked(g: NavGrid, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= g.w || y >= g.h) return true
  return g.blocked[y * g.w + x] === 1
}

export function isWalkable(g: NavGrid, x: number, y: number): boolean {
  return !isBlocked(g, x, y)
}

/** Nearest walkable tile to (x, y), searched in rings. Returns null if the room is solid. */
export function nearestWalkable(g: NavGrid, x: number, y: number): { x: number; y: number } | null {
  const sx = Math.max(0, Math.min(g.w - 1, Math.round(x)))
  const sy = Math.max(0, Math.min(g.h - 1, Math.round(y)))
  if (isWalkable(g, sx, sy)) return { x: sx, y: sy }
  for (let r = 1; r <= Math.max(g.w, g.h); r++) {
    for (let dy = -r; dy <= r; dy++) {
      for (let dx = -r; dx <= r; dx++) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) !== r) continue // ring only
        const nx = sx + dx
        const ny = sy + dy
        if (isWalkable(g, nx, ny)) return { x: nx, y: ny }
      }
    }
  }
  return null
}

/**
 * A* on the 4-neighbor grid. Returns the route INCLUDING the start and
 * goal tiles (both walkable — callers pass pre-snapped goals), or null
 * when unreachable. Deterministic: ties broken by insertion order.
 */
export function findPath(
  g: NavGrid,
  start: { x: number; y: number },
  goal: { x: number; y: number },
): { x: number; y: number }[] | null {
  if (!isWalkable(g, start.x, start.y) || !isWalkable(g, goal.x, goal.y)) return null
  if (start.x === goal.x && start.y === goal.y) return [{ ...start }]

  const w = g.w
  const n = w * g.h
  const startIdx = start.y * w + start.x
  const goalIdx = goal.y * w + goal.x

  const gCost = new Float64Array(n).fill(Infinity)
  const from = new Int32Array(n).fill(-1)
  const open: number[] = [startIdx]
  const inOpen = new Uint8Array(n)
  const closed = new Uint8Array(n)
  gCost[startIdx] = 0
  inOpen[startIdx] = 1

  const hDist = (idx: number): number => {
    const x = idx % w
    const y = (idx / w) | 0
    return Math.abs(x - goal.x) + Math.abs(y - goal.y)
  }

  while (open.length > 0) {
    // Linear scan min-f (fine for 20x20 rooms; keeps the module dependency-free)
    let bestK = 0
    let bestF = Infinity
    for (let i = 0; i < open.length; i++) {
      const idx = open[i]!
      const f = gCost[idx]! + hDist(idx)
      if (f < bestF) {
        bestF = f
        bestK = i
      }
    }
    const cur = open[bestK]!
    open.splice(bestK, 1)
    inOpen[cur] = 0
    if (cur === goalIdx) break
    closed[cur] = 1

    const cx = cur % w
    const cy = (cur / w) | 0
    const neighbors: [number, number][] = [
      [cx + 1, cy],
      [cx - 1, cy],
      [cx, cy + 1],
      [cx, cy - 1],
    ]
    for (const [nx, ny] of neighbors) {
      if (!isWalkable(g, nx, ny)) continue
      const nIdx = ny * w + nx
      if (closed[nIdx]) continue
      const tentative = gCost[cur]! + 1
      if (tentative < gCost[nIdx]!) {
        gCost[nIdx] = tentative
        from[nIdx] = cur
        if (!inOpen[nIdx]) {
          open.push(nIdx)
          inOpen[nIdx] = 1
        }
      }
    }
  }

  if (from[goalIdx] === -1 && goalIdx !== startIdx) return null

  // Reconstruct
  const path: { x: number; y: number }[] = []
  let cur = goalIdx
  while (cur !== -1) {
    path.push({ x: cur % w, y: (cur / w) | 0 })
    if (cur === startIdx) break
    cur = from[cur]!
  }
  path.reverse()
  return path
}

/**
 * Collapse collinear runs so the path turns only where it must.
 * Keeps start and goal.
 */
export function smooth(
  path: { x: number; y: number }[],
): { x: number; y: number }[] {
  if (path.length <= 2) return path
  const out: { x: number; y: number }[] = [path[0]!]
  for (let i = 1; i < path.length - 1; i++) {
    const a = out[out.length - 1]!
    const b = path[i]!
    const c = path[i + 1]!
    const abx = Math.sign(b.x - a.x)
    const aby = Math.sign(b.y - a.y)
    const bcx = Math.sign(c.x - b.x)
    const bcy = Math.sign(c.y - b.y)
    if (abx === bcx && aby === bcy) continue // same direction — skip b
    out.push(b)
  }
  out.push(path[path.length - 1]!)
  return out
}

/** Full route: snap endpoints, A*, smooth. Waypoints are tile centers. */
export function route(
  g: NavGrid,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
): { tx: number; ty: number }[] | null {
  const s = nearestWalkable(g, fromX, fromY)
  const t = nearestWalkable(g, toX, toY)
  if (!s || !t) return null
  const raw = findPath(g, s, t)
  if (!raw) return null
  const pts = smooth(raw)
  // Drop the first waypoint if we're already (approximately) on it — the
  // person walks toward the *next* tile center, not backward into their own tile.
  const out: { tx: number; ty: number }[] = []
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i]!
    if (i === 0 && Math.abs(p.x - fromX) < 0.55 && Math.abs(p.y - fromY) < 0.55) continue
    out.push({ tx: p.x, ty: p.y })
  }
  if (out.length === 0) out.push({ tx: s.x, ty: s.y })
  return out
}
