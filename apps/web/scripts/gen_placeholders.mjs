/**
 * Generate placeholder room background PNGs for the pre-rendered migration.
 *
 * Each room gets a flat-colored isometric diamond with walls,
 * sized to match its tile footprint. Background is #080D16.
 *
 * Usage: node scripts/gen_placeholders.mjs
 */

import { createCanvas } from '@napi-rs/canvas'
import { writeFileSync, mkdirSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, '..', 'public', 'assets', 'office', 'rooms')
mkdirSync(OUT_DIR, { recursive: true })

const TW = 64
const TH = 32
const WALL_H = 62
const BG = '#080D16'

const ROOMS = [
  { id: 'ceo_office', o: [2, 2], s: [10, 8], floor: '#9C7B50' },
  { id: 'managers', o: [18, 2], s: [12, 7], floor: '#4B6578' },
  { id: 'dev_floor', o: [30, 8], s: [20, 20], floor: '#C7B698' },
  { id: 'devops', o: [2, 14], s: [10, 8], floor: '#8C7A66' },
  { id: 'meeting_room', o: [8, 26], s: [16, 12], floor: '#53718B' },
]

function iso(tx, ty) {
  return { x: (tx - ty) * (TW / 2), y: (tx + ty) * (TH / 2) }
}

for (const room of ROOMS) {
  const [ox, oy] = room.o
  const [w, h] = room.s

  // Calculate bounds of the room in world space (including walls)
  const corners = [
    iso(ox - 1, oy - 1),
    iso(ox + w, oy - 1),
    iso(ox + w, oy + h),
    iso(ox - 1, oy + h),
  ]

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const c of corners) {
    minX = Math.min(minX, c.x - TW / 2)
    maxX = Math.max(maxX, c.x + TW / 2)
    minY = Math.min(minY, c.y - WALL_H - 20)
    maxY = Math.max(maxY, c.y + TH + 20)
  }

  const pad = 20
  minX -= pad; minY -= pad; maxX += pad; maxY += pad

  const imgW = Math.ceil(maxX - minX)
  const imgH = Math.ceil(maxY - minY)

  const canvas = createCanvas(imgW, imgH)
  const ctx = canvas.getContext('2d')

  // Fill with canvas background color
  ctx.fillStyle = BG
  ctx.fillRect(0, 0, imgW, imgH)

  // Translate so room origin maps correctly
  ctx.translate(-minX, -minY)

  // Draw floor tiles
  for (let i = 0; i < w; i++) {
    for (let j = 0; j < h; j++) {
      const p = iso(ox + i, oy + j)
      ctx.fillStyle = (i + j) % 2 === 0 ? room.floor : darken(room.floor, 0.92)
      ctx.beginPath()
      ctx.moveTo(p.x, p.y - TH / 2)
      ctx.lineTo(p.x + TW / 2, p.y)
      ctx.lineTo(p.x, p.y + TH / 2)
      ctx.lineTo(p.x - TW / 2, p.y)
      ctx.closePath()
      ctx.fill()
    }
  }

  // Draw walls (back and left) as simple colored blocks
  const wallColor = '#6B3A2A'
  const wallDark = '#4A2418'

  // Back wall
  for (let i = -1; i < w; i++) {
    const p = iso(ox + i, oy - 1)
    const p2 = iso(ox + i + 1, oy - 1)
    ctx.fillStyle = wallColor
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(p2.x, p2.y)
    ctx.lineTo(p2.x, p2.y - WALL_H)
    ctx.lineTo(p.x, p.y - WALL_H)
    ctx.closePath()
    ctx.fill()
  }

  // Left wall
  for (let j = 0; j < h; j++) {
    const p = iso(ox - 1, oy + j)
    const p2 = iso(ox - 1, oy + j + 1)
    ctx.fillStyle = wallDark
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(p2.x, p2.y)
    ctx.lineTo(p2.x, p2.y - WALL_H)
    ctx.lineTo(p.x, p.y - WALL_H)
    ctx.closePath()
    ctx.fill()
  }

  // Draw room label
  ctx.fillStyle = 'rgba(255,255,255,0.6)'
  ctx.font = 'bold 24px sans-serif'
  ctx.textAlign = 'center'
  const labelPos = iso(ox + w / 2, oy + h + 0.5)
  ctx.fillText(room.id.toUpperCase().replace('_', ' '), labelPos.x, labelPos.y)

  // Write PNG
  const buf = canvas.toBuffer('image/png')
  const outPath = join(OUT_DIR, `${room.id}.png`)
  writeFileSync(outPath, buf)
  console.log(`✓ ${room.id}: ${imgW}×${imgH}px → ${outPath}`)

  // Store calibration info
  const origin = iso(ox, oy)
  console.log(`  anchor: iso(${ox},${oy}) = (${origin.x}, ${origin.y})`)
  console.log(`  image offset: dx=${origin.x - minX}, dy=${origin.y - minY}`)
}

function darken(hex, k) {
  const n = parseInt(hex.slice(1), 16)
  const r = Math.min(255, ((n >> 16) & 255) * k) | 0
  const g = Math.min(255, ((n >> 8) & 255) * k) | 0
  const b = Math.min(255, (n & 255) * k) | 0
  return `rgb(${r},${g},${b})`
}
