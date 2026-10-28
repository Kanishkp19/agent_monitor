/**
 * Internal types for the office simulation.
 *
 * Strictly isolated: no network, API, or WebSocket imports.
 */

export type CharacterArchetype =
  | 'exec'
  | 'manager'
  | 'senior_engineer'
  | 'engineer'
  | 'intern'
  | 'devops'

export type SimFsmState =
  | 'idle'
  | 'walking'
  | 'working'
  | 'waiting'
  | 'blocked'
  | 'meeting'

export type SimBadge = 'none' | 'working' | 'waiting' | 'blocked' | 'anomaly'

export type AgentBrand = 'claude_code' | 'codex' | 'internal' | 'mcp'

/** Compass facing — matches the atlas direction suffixes (s/w/n/e). */
export type Facing = 'n' | 'e' | 's' | 'w'

/**
 * What the body is doing — orthogonal to `fsm`, which is what the *governance
 * plane* thinks the person is doing. The behavior system derives `activity`
 * from `fsm` plus wander logic (blocked people pace, waiting people stroll,
 * approved people chat on the way to the coffee machine).
 */
export type Activity =
  | 'desk' // seated/standing at own desk, typing
  | 'walk' // following a path
  | 'wander' // pacing near the current spot (blocked)
  | 'stand' // paused mid-walk (waiting, break)
  | 'sit' // seated away from a desk (meeting room, lounge)
  | 'break' // at the coffee machine / water cooler
  | 'chat' // standing conversation with another employee

/** A single leg of a walk: move toward this tile center. */
export interface Waypoint {
  tx: number
  ty: number
}

/**
 * Path-following movement. `path` is the remaining tile route; the person is
 * always between `path[0]` (current segment target) and their position.
 */
export interface SimPathMove {
  path: Waypoint[]
  /** Speed in tiles per second (before global speed multiplier). */
  speed: number
  /** Called when the last waypoint is reached. */
  after?: () => void
}

/** Straight-line hop across one tile (non-navigating; e.g. sitting down). */
export interface SimMotion {
  fromX: number
  fromY: number
  toX: number
  toY: number
  start: number
  dur: number
  after?: () => void
}

export interface SimDecision {
  t: string
  what: string
  k: 'allow' | 'block' | 'review' | 'redact'
}

export interface SimTask {
  title: string
  repo?: string
  env?: string
}

export interface SimBubble {
  text: string
  until: number
}

export interface SimEmployeeToday {
  requests: number
  tokens: number
  cost: number
  allowed: number
  blocked: number
  review: number
  sessions: number
}

export interface SimEmployee {
  id: string
  name: string
  first: string
  role: string
  team: string
  agent: AgentBrand
  room: string
  /** Home anchor: the desk/seat tile the person belongs to. */
  at: [number, number]
  facing: Facing
  shirt: string
  skin: string
  hair: string
  fsm: SimFsmState
  anomaly: boolean
  risk: number
  today: SimEmployeeToday
  decisions: SimDecision[]
  task: SimTask | null
  bubble: SimBubble | null
  pos: { x: number; y: number }
  /** Straight-line micro movement (sit down / stand up). */
  moving: SimMotion | null
  /** Tile-path navigation. */
  path: SimPathMove | null
  animKind: 'idle' | 'walk' | 'type'
  /** Shared animation clock in seconds (phase, not wall time). */
  animPhase: number
  /** 0..1 progress through the current walk stride; drives frame selection. */
  stride: number
  activity: Activity
  /** What the person was doing before the current interruption (return target). */
  homeActivity: Activity
  /** Set while a behavior owns the person (break, chat, pacing). */
  behavior: string | null
  /** When the current behavior ends (ms clock, sim-speed aware via ticks). */
  behaviorUntil: number
  /** Facing target while chatting (tile of the partner). */
  chatWith: string | null
  /** Internal: next scheduled micro-action (ms clock). */
  _nextWander: number
  /** Internal: per-behavior scratch (e.g. pacing anchor). */
  _wanderHome: [number, number] | null
  showWorking?: boolean
  /** Atlas look index (0..7). Deterministic per employee. */
  look: number
  archetype?: CharacterArchetype
  seatType?: string
}

export interface PropItem {
  type: string
  tx: number
  ty: number
  big?: boolean
  owner?: string
}

export interface RoomSpec {
  id: string
  label: string
  o: [number, number]
  s: [number, number]
  floor: [string, string]
  labelAt: [number, number]
}
