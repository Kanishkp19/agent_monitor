/**
 * 2:1 Isometric coordinate projection and drawing primitives.
 */

export const TW = 64
export const TH = 32
export const WALL_H = 62

export const BRICK = ['#8E4C3C', '#96523F', '#874536', '#9A5744', '#823F33']
export const MORTAR = '#5E3229'
export const SLAB = '#2B1F1A'
export const SLAB_HI = '#3A2A22'

export function iso(tx: number, ty: number): { x: number; y: number } {
  return {
    x: (tx - ty) * (TW / 2),
    y: (tx + ty) * (TH / 2),
  }
}

export function depth(tx: number, ty: number, layer = 0): number {
  return (tx + ty) * 10 + layer
}

export function tint(hex: string, k: number): string {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.min(255, ((n >> 16) & 255) * k) | 0
  const g = Math.min(255, ((n >> 8) & 255) * k) | 0
  const b = Math.min(255, (n & 255) * k) | 0
  return `rgb(${r},${g},${b})`
}

export function quad(c: CanvasRenderingContext2D, pts: [number, number][], fill: string): void {
  const first = pts[0]
  if (!first) return
  c.beginPath()
  c.moveTo(first[0], first[1])
  for (let i = 1; i < pts.length; i++) {
    const pt = pts[i]
    if (pt) c.lineTo(pt[0], pt[1])
  }
  c.closePath()
  c.fillStyle = fill
  c.fill()
}

export function diamond(
  c: CanvasRenderingContext2D,
  tx: number,
  ty: number,
  fill: string,
  line?: string | null,
): void {
  const p = iso(tx, ty)
  const hx = TW / 2
  const hy = TH / 2
  quad(
    c,
    [
      [p.x, p.y - hy],
      [p.x + hx, p.y],
      [p.x, p.y + hy],
      [p.x - hx, p.y],
    ],
    fill,
  )
  if (line) {
    c.strokeStyle = line
    c.lineWidth = 1
    c.stroke()
  }
}

export function box(
  c: CanvasRenderingContext2D,
  tx: number,
  ty: number,
  w: number,
  d: number,
  h: number,
  top: string,
  left: string,
  right: string,
): void {
  const A = iso(tx, ty)
  const B = iso(tx + w, ty)
  const C = iso(tx + w, ty + d)
  const D = iso(tx, ty + d)
  quad(c, [[B.x, B.y - h], [C.x, C.y - h], [C.x, C.y], [B.x, B.y]], right)
  quad(c, [[D.x, D.y - h], [C.x, C.y - h], [C.x, C.y], [D.x, D.y]], left)
  quad(c, [[A.x, A.y - h], [B.x, B.y - h], [C.x, C.y - h], [D.x, D.y - h]], top)
}

export function wallFace(tx: number, ty: number, side: 'back' | 'left'): {
  O: { x: number; y: number }
  u: { x: number; y: number }
} {
  if (side === 'back') {
    const O = iso(tx, ty + 1)
    return { O, u: { x: TW / 2, y: TH / 2 } }
  }
  const O = iso(tx + 1, ty)
  return { O, u: { x: -TW / 2, y: TH / 2 } }
}

export function onFace(
  f: { O: { x: number; y: number }; u: { x: number; y: number } },
  s: number,
  t: number,
): [number, number] {
  return [f.O.x + f.u.x * s, f.O.y + f.u.y * s - t]
}

export function drawWall(
  c: CanvasRenderingContext2D,
  tx: number,
  ty: number,
  side: 'back' | 'left',
): void {
  const f = wallFace(tx, ty, side)
  const shade = side === 'left' ? 0.82 : 1
  quad(c, [onFace(f, 0, 0), onFace(f, 1, 0), onFace(f, 1, WALL_H), onFace(f, 0, WALL_H)], MORTAR)
  const rows = 7
  const rh = WALL_H / rows
  for (let r = 0; r < rows; r++) {
    const t0 = r * rh + 1
    const t1 = (r + 1) * rh - 0.5
    const off = r % 2 ? -0.25 : 0
    for (let k = -1; k <= 2; k++) {
      let s0 = k * 0.5 + off
      let s1 = s0 + 0.5 - 0.022
      s0 = Math.max(0, s0)
      s1 = Math.min(1, s1)
      if (s1 <= s0) continue
      const pick = BRICK[Math.abs(tx * 7 + ty * 13 + r * 5 + k * 3) % BRICK.length] ?? '#8E4C3C'
      quad(c, [onFace(f, s0, t0), onFace(f, s1, t0), onFace(f, s1, t1), onFace(f, s0, t1)], tint(pick, shade))
    }
  }
  const th: [number, number] = side === 'back' ? [11, -6] : [-11, -6]
  const a = onFace(f, 0, WALL_H)
  const b = onFace(f, 1, WALL_H)
  quad(c, [a, b, [b[0] + th[0], b[1] + th[1]], [a[0] + th[0], a[1] + th[1]]], '#B4705C')
}

export function onWall(
  c: CanvasRenderingContext2D,
  tx: number,
  ty: number,
  side: 'back' | 'left',
  s0: number,
  s1: number,
  t0: number,
  t1: number,
  fill: string,
  frame?: string,
): void {
  const f = wallFace(tx, ty, side)
  const pts: [number, number][] = [onFace(f, s0, t0), onFace(f, s1, t0), onFace(f, s1, t1), onFace(f, s0, t1)]
  if (frame) {
    const g = 0.06
    const gt = 3
    quad(c, [onFace(f, s0 - g, t0 - gt), onFace(f, s1 + g, t0 - gt), onFace(f, s1 + g, t1 + gt), onFace(f, s0 - g, t1 + gt)], frame)
  }
  quad(c, pts, fill)
}
