/**
 * Event payload types.
 *
 * GENERATED FROM packages/contracts/events.schema.json -- DO NOT EDIT
 *
 * Regenerate with `python tasks.py contracts`.
 */

export interface PolicyMatch {
  policy_id: string
  version: number
  effect: string
  priority: number
}

export interface MaskedFinding {
  detector: string
  masked: string
}

export interface RiskFactor {
  feature: string
  value: number
  z: number
  contribution?: number
  explanation: string
}

/**
 * `sim.tick` -- emitted by sim/engine.py.
 */
export interface SimTickPayload {
  sim_ts: number
  active_sessions: number
  queued_tasks: number
}

/**
 * `sim.day.completed` -- emitted by sim/engine.py.
 */
export interface SimDayCompletedPayload {
  sim_day: number
  tasks: number
  events: number
  cost_usd: number
  blocked: number
  approvals: number
  incidents: number
}

/**
 * `sim.meeting.started` -- emitted by sim/scenarios.py.
 *
 * Purely cosmetic. Moves avatars to the meeting room; no governed outcome depends on it.
 */
export interface SimMeetingStartedPayload {
  meeting_id: string
  attendees: string[]
  room?: string
}

/**
 * `sim.meeting.ended` -- emitted by sim/scenarios.py.
 */
export interface SimMeetingEndedPayload {
  meeting_id: string
  attendees: string[]
}

/**
 * `task.requested` -- emitted by sim/engine.py, /ingest/gate1.
 */
export interface TaskRequestedPayload {
  task_id: string
  employee_id: string
  title: string
  task_type: string
  complexity: string
  repo: string
  environment: string
  is_marquee: boolean
}

/**
 * `gate1.decision` -- emitted by the gate1 caller.
 *
 * findings carry the masked form only. A raw secret value never appears in an event payload, a log line, or anything sent to the frontend.
 */
export interface Gate1DecisionPayload {
  task_id: string
  request_id: string
  decision: string
  reason_code: string
  matched_policies: PolicyMatch[]
  est_input_tokens?: number
  est_output_tokens?: number
  est_cost_usd?: number
  routed_model: string
  findings?: MaskedFinding[]
  budget_remaining_usd?: number
  latency_ms: number
}

/**
 * `model.invoked` -- emitted by agent/runner.py.
 */
export interface ModelInvokedPayload {
  task_id: string
  model_id: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  iteration: number
  stop_reason: string
  fallback: boolean
}

/**
 * `action.requested` -- emitted by agent/runner.py.
 */
export interface ActionRequestedPayload {
  task_id: string
  action_id: string
  tool: string
  target_resource: string
  environment: string
  resource_sensitivity: string
  args_digest: string
  iteration: number
}

/**
 * `gate2.decision` -- emitted by the gate2 caller.
 */
export interface Gate2DecisionPayload {
  task_id: string
  action_id: string
  tool: string
  decision: string
  reason_code: string
  matched_policies: PolicyMatch[]
  target_resource: string
  environment: string
  repeat_count_5m?: number
  latency_ms: number
}

/**
 * `approval.requested` -- emitted by governance/approvals.py.
 */
export interface ApprovalRequestedPayload {
  approval_id: string
  task_id: string
  action_id: string
  requester_id: string
  approver_role?: string
  approver_scope?: string
  reason: string
  risk_at_request?: number
  cost_so_far_usd?: number
  expires_sim_ts: number
}

/**
 * `approval.decided` -- emitted by governance/approvals.py.
 */
export interface ApprovalDecidedPayload {
  approval_id: string
  task_id: string
  status: string
  approver_id?: string
  note?: string
  latency_sim_s: number
}

/**
 * `sandbox.executed` -- emitted by sandbox/.
 */
export interface SandboxExecutedPayload {
  task_id: string
  action_id: string
  tool: string
  ok: boolean
  duration_ms: number
  output_preview?: string
}

/**
 * `action.blocked` -- emitted by agent/runner.py.
 */
export interface ActionBlockedPayload {
  task_id: string
  action_id: string
  tool: string
  target_resource: string
  policy_id?: string
  message: string
}

/**
 * `task.completed` -- emitted by agent/runner.py.
 */
export interface TaskCompletedPayload {
  task_id: string
  employee_id: string
  status: string
  tokens_in: number
  tokens_out: number
  cost_usd: number
  actions_total: number
  actions_blocked: number
  duration_sim_s: number
}

/**
 * `budget.exceeded` -- emitted by the budget caller.
 */
export interface BudgetExceededPayload {
  employee_id: string
  scope: 'employee' | 'team'
  budget_usd: number
  spend_usd: number
  sim_date: string
}

/**
 * `risk.updated` -- emitted by the risk scoring caller.
 *
 * The office applies an anomaly overlay at score >= 70 and clears it below 60. The overlay is not a state: an employee can be visibly working and flagged at the same time, which is the most interesting thing the demo can show.
 */
export interface RiskUpdatedPayload {
  employee_id: string
  score: number
  static: number
  behavioural: number
  ml: number
  confidence: string
  top_factors?: RiskFactor[]
  delta?: number
}

/**
 * `incident.opened` -- emitted by risk/incidents.py.
 */
export interface IncidentOpenedPayload {
  incident_id: string
  employee_id: string
  detector: string
  score: number
  summary: string
  evidence_count: number
}

/**
 * `autopilot.state` -- emitted by autopilot/runner.py.
 */
export interface AutopilotStatePayload {
  state: string
}

/**
 * `autopilot.gate` -- emitted by autopilot/runner.py.
 */
export interface AutopilotGatePayload {
  gate: number
  tool?: string
  path?: string
  decision: string
  reason: string
}

/**
 * `autopilot.model` -- emitted by autopilot/runner.py.
 */
export interface AutopilotModelPayload {
  provider: string
  model_id: string
  tokens_in: number
  tokens_out: number
  latency_ms: number
  retry_count?: number
  is_mock: boolean
}

/**
 * `autopilot.action` -- emitted by autopilot/runner.py.
 */
export interface AutopilotActionPayload {
  tool: string
  args?: string
  decision: string
  result: Record<string, unknown>
}

/**
 * `autopilot.test` -- emitted by autopilot/runner.py.
 */
export interface AutopilotTestPayload {
  phase: string
  passed: boolean
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
  timed_out?: boolean
  summary_line?: string
}

/**
 * `audit.raw_access` -- emitted by the blob store reader.
 *
 * The blob store is the only home for raw prompts, and every read of one is audited. Without this the redaction guarantee is unverifiable.
 */
export interface AuditRawAccessPayload {
  task_id: string
  blob_key: string
  actor_id: string
  reason?: string
}

export type EventDetailType =
  | 'sim.tick'
  | 'sim.day.completed'
  | 'sim.meeting.started'
  | 'sim.meeting.ended'
  | 'task.requested'
  | 'gate1.decision'
  | 'model.invoked'
  | 'action.requested'
  | 'gate2.decision'
  | 'approval.requested'
  | 'approval.decided'
  | 'sandbox.executed'
  | 'action.blocked'
  | 'task.completed'
  | 'budget.exceeded'
  | 'risk.updated'
  | 'incident.opened'
  | 'autopilot.state'
  | 'autopilot.gate'
  | 'autopilot.model'
  | 'autopilot.action'
  | 'autopilot.test'
  | 'audit.raw_access'

export interface EventPayloadMap {
  'sim.tick': SimTickPayload
  'sim.day.completed': SimDayCompletedPayload
  'sim.meeting.started': SimMeetingStartedPayload
  'sim.meeting.ended': SimMeetingEndedPayload
  'task.requested': TaskRequestedPayload
  'gate1.decision': Gate1DecisionPayload
  'model.invoked': ModelInvokedPayload
  'action.requested': ActionRequestedPayload
  'gate2.decision': Gate2DecisionPayload
  'approval.requested': ApprovalRequestedPayload
  'approval.decided': ApprovalDecidedPayload
  'sandbox.executed': SandboxExecutedPayload
  'action.blocked': ActionBlockedPayload
  'task.completed': TaskCompletedPayload
  'budget.exceeded': BudgetExceededPayload
  'risk.updated': RiskUpdatedPayload
  'incident.opened': IncidentOpenedPayload
  'autopilot.state': AutopilotStatePayload
  'autopilot.gate': AutopilotGatePayload
  'autopilot.model': AutopilotModelPayload
  'autopilot.action': AutopilotActionPayload
  'autopilot.test': AutopilotTestPayload
  'audit.raw_access': AuditRawAccessPayload
}

export const EVENT_TYPES: readonly EventDetailType[] = [
  'sim.tick',
  'sim.day.completed',
  'sim.meeting.started',
  'sim.meeting.ended',
  'task.requested',
  'gate1.decision',
  'model.invoked',
  'action.requested',
  'gate2.decision',
  'approval.requested',
  'approval.decided',
  'sandbox.executed',
  'action.blocked',
  'task.completed',
  'budget.exceeded',
  'risk.updated',
  'incident.opened',
  'autopilot.state',
  'autopilot.gate',
  'autopilot.model',
  'autopilot.action',
  'autopilot.test',
  'audit.raw_access',
] as const

/**
 * The events the office renderer reacts to.
 *
 * Everything else still reaches the Live Feed; the canvas ignores it.
 * Keeping this list short is what keeps the event pump inside its
 * budget of twelve events per frame.
 */
export const OFFICE_EVENT_TYPES: ReadonlySet<EventDetailType> = new Set([
  'sim.meeting.started',
  'sim.meeting.ended',
  'task.requested',
  'gate1.decision',
  'gate2.decision',
  'approval.requested',
  'approval.decided',
  'task.completed',
  'risk.updated',
])

/** The EventBridge-shaped envelope every event travels in. */
export interface EventDetail {
  run_id: string
  seq: number
  sim_ts: number
  employee_id: string | null
  task_id: string | null
  payload: Record<string, unknown>
}

export interface EventEnvelope {
  id: string
  source: string
  detail_type: EventDetailType
  time: string
  detail: EventDetail
}
