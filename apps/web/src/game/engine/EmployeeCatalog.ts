/**
 * The 20 employees of AgentShield.
 *
 * Deterministic styling matching h.html and backend seed_data.py.
 */

import type { AgentBrand, CharacterArchetype, SimEmployee } from '../systems/Types'

export const SHIRTS = ['#3D6BB5', '#4A8A6F', '#8E4F6E', '#5B5F8C', '#A05B3C', '#3F7A8E']
export const SKINS = ['#C98D63', '#E0AE86', '#A76B45', '#D79C74']
export const HAIRS = ['#1E1712', '#2C2119', '#3E2B1E', '#141014']

type RawEmployee = [
  string, // id
  string, // name
  string, // role
  string, // team
  AgentBrand, // agent
  string, // room
  [number, number], // at
  'n' | 'e' | 's' | 'w', // facing
]

export const RAW_EMPLOYEES: RawEmployee[] = [
  ['emp_001', 'Vikram Nair', 'CEO', 'exec', 'internal', 'ceo_office', [25, 16], 'e'],
  ['emp_002', 'Sara Iyer', 'Senior Manager', 'platform', 'claude_code', 'managers', [25.66, 6.0], 'n'],
  ['emp_003', 'Ben Mathew', 'Manager', 'payments', 'claude_code', 'managers', [26.66, 3.0], 'e'],
  ['emp_004', 'Sarah Khan', 'Senior Eng.', 'payments', 'claude_code', 'dev_floor', [2.47, 2.84], 'e'],
  ['emp_005', 'Arjun Menon', 'Senior Eng.', 'platform', 'codex', 'dev_floor', [6.47, 2.84], 'e'],
  ['emp_006', 'Neha Gupta', 'Senior Eng.', 'data', 'claude_code', 'dev_floor', [10.47, 2.84], 'e'],
  ['emp_007', 'Priya Sharma', 'Engineer', 'payments', 'codex', 'dev_floor', [14.47, 2.84], 'e'],
  ['emp_008', 'Aman Verma', 'Engineer', 'payments', 'codex', 'dev_floor', [2.47, 7.84], 'e'],
  ['emp_009', 'Rohit Das', 'Engineer', 'platform', 'claude_code', 'dev_floor', [6.47, 7.84], 'e'],
  ['emp_012', 'Ananya Roy', 'Engineer', 'data', 'codex', 'dev_floor', [10.47, 7.84], 'e'],
  ['emp_013', 'Rahul Sharma', 'Engineering Intern', 'payments', 'codex', 'dev_floor', [14.47, 7.84], 'e'],
  ['emp_014', 'Ishaan Bose', 'Engineering Intern', 'payments', 'codex', 'dev_floor', [2.47, 12.84], 'e'],
  ['emp_017', 'Nikhil Rao', 'Engineer', 'platform', 'internal', 'dev_floor', [6.47, 12.84], 'e'],
  ['emp_018', 'Zoya Ahmed', 'Engineering Intern', 'platform', 'claude_code', 'dev_floor', [10.47, 12.84], 'e'],
  ['emp_020', 'Lakshmi Iyer', 'Engineer', 'data', 'claude_code', 'dev_floor', [14.47, 12.84], 'e'],
  ['emp_019', 'Mark Dsouza', 'DevOps', 'platform', 'internal', 'devops', [26.0, 24.0], 'n'],
  ['emp_010', 'Meera Pillai', 'Engineer', 'frontend', 'claude_code', 'meeting_room', [4.02, 20.0], 's'],
  ['emp_011', 'Kabir Shah', 'Engineer', 'frontend', 'mcp', 'meeting_room', [6.42, 20.0], 's'],
  ['emp_015', 'Tara Nair', 'Engineering Intern', 'frontend', 'claude_code', 'meeting_room', [4.02, 28.0], 'n'],
  ['emp_016', 'Dev Malhotra', 'Engineering Intern', 'data', 'codex', 'meeting_room', [6.42, 28.0], 'n'],
]

const INITIAL_RISKS = [12, 18, 24, 31, 27, 22, 29, 34, 26, 19, 61, 47, 38, 21, 25, 33, 17, 23, 28, 30]

export const EMPLOYEE_SPRITE_MAP: Record<string, { col: number; row: number }> = {
  emp_001: { col: 1, row: 0 },
  emp_002: { col: 4, row: 0 },
  emp_003: { col: 7, row: 0 },
  emp_004: { col: 10, row: 0 },
  emp_005: { col: 13, row: 0 },
  emp_006: { col: 1, row: 4 },
  emp_007: { col: 4, row: 4 },
  emp_008: { col: 7, row: 4 },
  emp_009: { col: 10, row: 4 },
  emp_010: { col: 13, row: 4 },
  emp_011: { col: 1, row: 8 },
  emp_012: { col: 4, row: 8 },
  emp_013: { col: 7, row: 8 },
  emp_014: { col: 10, row: 8 },
  emp_015: { col: 13, row: 8 },
  emp_016: { col: 1, row: 12 },
  emp_017: { col: 4, row: 12 },
  emp_018: { col: 7, row: 12 },
  emp_019: { col: 10, row: 12 },
  emp_020: { col: 13, row: 12 },
}

/**
 * Atlas look per employee: role-flavoured, deterministic.
 * Looks: 0 exec-grey, 1 manager-navy, 2 senior-teal, 3 engineer-steel,
 * 4 engineer-plum, 5 intern-blue, 6 devops-slate, 7 engineer-auburn.
 */
const LOOK_ASSIGNMENT: Record<string, number> = {
  emp_001: 0, // CEO
  emp_002: 1, // senior manager
  emp_003: 1, // manager
  emp_004: 3,
  emp_005: 2,
  emp_006: 4,
  emp_007: 7,
  emp_008: 3,
  emp_009: 2,
  emp_012: 4,
  emp_013: 5, // intern
  emp_014: 5, // intern
  emp_017: 3,
  emp_018: 7,
  emp_020: 2,
  emp_019: 6, // devops
  emp_010: 4,
  emp_011: 3,
  emp_015: 7,
  emp_016: 5,
}

function getLookFallback(employeeId: string): number {
  const digits = employeeId.replace(/\D/g, '')
  const num = digits ? parseInt(digits, 10) : 0
  return num % 8
}

export function getEmployeeSprite(employeeId: string): { col: number; row: number } {
  if (EMPLOYEE_SPRITE_MAP[employeeId]) {
    return EMPLOYEE_SPRITE_MAP[employeeId]
  }
  const digits = employeeId.replace(/\D/g, '')
  const num = digits ? Math.max(0, parseInt(digits, 10) - 1) : 0
  const col = (num % 5) * 3 + 1
  const row = (Math.floor(num / 5) % 4) * 4
  return { col, row }
}

export function getArchetype(role: string, team: string): CharacterArchetype {
  const r = role.toLowerCase()
  const t = team.toLowerCase()
  if (r.includes('ceo') || t === 'exec') return 'exec'
  if (r.includes('manager')) return 'manager'
  if (r.includes('senior')) return 'senior_engineer'
  if (r.includes('intern')) return 'intern'
  if (r.includes('devops')) return 'devops'
  return 'engineer'
}

export function getSeatType(room: string, _id: string, facing: 'n' | 'e' | 's' | 'w'): string {
  if (room === 'ceo_office') return 'exec'
  if (room === 'managers') {
    return facing === 'n' ? 'mgr_n' : 'mgr_e'
  }
  if (room === 'devops') return 'devops'
  if (room === 'meeting_room') {
    return facing === 's' ? 'conf_near' : 'conf_far'
  }
  return 'desk_e'
}

export function createDefaultEmployees(): SimEmployee[] {
  return RAW_EMPLOYEES.map(([id, name, role, team, agent, room, at, facing], i) => {
    const sprite = getEmployeeSprite(id)
    return {
      id,
      name,
      role,
      team,
      agent,
      room,
      at,
      facing,
      first: name.split(' ')[0] ?? name,
      shirt: SHIRTS[i % SHIRTS.length] ?? '#3D6BB5',
      skin: SKINS[(i * 3) % SKINS.length] ?? '#C98D63',
      hair: HAIRS[(i * 5) % HAIRS.length] ?? '#1E1712',
      fsm: room === 'meeting_room' ? 'meeting' : 'idle',
      anomaly: false,
      risk: INITIAL_RISKS[i] ?? 20,
      today: { requests: 0, tokens: 0, cost: 0, allowed: 0, blocked: 0, review: 0, sessions: 0 },
      decisions: [],
      task: null,
      bubble: null,
      pos: { x: at[0], y: at[1] },
      moving: null,
      path: null,
      animKind: 'idle',
      animPhase: Math.random() * 6.28,
      stride: 0,
      activity: room === 'meeting_room' ? 'sit' : 'desk',
      homeActivity: room === 'meeting_room' ? 'sit' : 'desk',
      behavior: null,
      behaviorUntil: 0,
      chatWith: null,
      _nextWander: 2 + Math.random() * 8,
      _wanderHome: null,
      spriteCol: sprite.col,
      spriteRow: sprite.row,
      look: LOOK_ASSIGNMENT[id] ?? getLookFallback(id),
      archetype: getArchetype(role, team),
      seatType: getSeatType(room, id, facing),
    }
  })
}
