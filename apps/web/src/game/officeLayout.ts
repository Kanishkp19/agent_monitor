export type OfficeState = 'idle' | 'working' | 'waiting' | 'blocked' | 'meeting' | 'walking'

export interface TilePosition {
  x: number
  y: number
}

export interface OfficeRoom {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
  colour: number
}

export interface OfficeDesk extends TilePosition {
  id: string
  name: string
  roomId: string
}

export const TILE_WIDTH = 64
export const TILE_HEIGHT = 32

export const OFFICE_ROOMS: OfficeRoom[] = [
  { id: 'ceo', label: 'CEO OFFICE', x: 3, y: 3, width: 8, height: 7, colour: 0xb89665 },
  { id: 'managers', label: 'MANAGERS', x: 13, y: 3, width: 12, height: 7, colour: 0x7590a4 },
  { id: 'devops', label: 'DEVOPS', x: 3, y: 13, width: 8, height: 8, colour: 0x7991a1 },
  { id: 'meeting', label: 'MEETING ROOM', x: 13, y: 13, width: 12, height: 12, colour: 0x6f88a8 },
  { id: 'development', label: 'DEVELOPMENT FLOOR', x: 28, y: 3, width: 17, height: 20, colour: 0xb9a384 },
]

export const OFFICE_DESKS: OfficeDesk[] = [
  { id: 'emp_001', name: 'Vikram', roomId: 'ceo', x: 6, y: 6 },
  { id: 'emp_002', name: 'Sara', roomId: 'managers', x: 17, y: 6 },
  { id: 'emp_003', name: 'Ben', roomId: 'managers', x: 21, y: 6 },
  { id: 'emp_019', name: 'Mark', roomId: 'devops', x: 6, y: 17 },
  { id: 'emp_014', name: 'Lucas', roomId: 'devops', x: 8, y: 19 },
  { id: 'emp_010', name: 'Meera', roomId: 'meeting', x: 16, y: 19 },
  { id: 'emp_011', name: 'Kabir', roomId: 'meeting', x: 20, y: 19 },
  { id: 'emp_015', name: 'Tara', roomId: 'meeting', x: 16, y: 22 },
  { id: 'emp_016', name: 'Dev', roomId: 'meeting', x: 20, y: 22 },
  { id: 'emp_004', name: 'Sarah', roomId: 'development', x: 32, y: 7 },
  { id: 'emp_005', name: 'Arjun', roomId: 'development', x: 36, y: 7 },
  { id: 'emp_006', name: 'Neha', roomId: 'development', x: 40, y: 7 },
  { id: 'emp_007', name: 'Priya', roomId: 'development', x: 32, y: 12 },
  { id: 'emp_008', name: 'Aman', roomId: 'development', x: 36, y: 12 },
  { id: 'emp_009', name: 'Rohit', roomId: 'development', x: 40, y: 12 },
  { id: 'emp_012', name: 'Ananya', roomId: 'development', x: 32, y: 17 },
  { id: 'emp_013', name: 'Rahul', roomId: 'development', x: 36, y: 17 },
  { id: 'emp_017', name: 'Nikhil', roomId: 'development', x: 40, y: 17 },
  { id: 'emp_018', name: 'Zoya', roomId: 'development', x: 32, y: 20 },
  { id: 'emp_020', name: 'Lakshmi', roomId: 'development', x: 40, y: 20 },
]

export const MEETING_SEATS: TilePosition[] = [
  { x: 16, y: 18 }, { x: 18, y: 18 }, { x: 20, y: 18 },
  { x: 16, y: 22 }, { x: 18, y: 22 }, { x: 20, y: 22 },
]

export const APPROVAL_POINTS: Record<string, TilePosition> = {
  ceo: { x: 8, y: 8 }, managers: { x: 23, y: 8 }, devops: { x: 8, y: 15 },
  meeting: { x: 22, y: 16 }, development: { x: 42, y: 18 },
}

export function tileToWorld(tile: TilePosition): TilePosition {
  return { x: (tile.x - tile.y) * (TILE_WIDTH / 2), y: (tile.x + tile.y) * (TILE_HEIGHT / 2) }
}

export function depthFor(tile: TilePosition, layer = 0): number {
  return (tile.x + tile.y) * 10 + layer
}
