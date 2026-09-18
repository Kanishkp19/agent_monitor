/**
 * Typed fetch against the AgentShield API.
 *
 * Every non-2xx body is the error envelope from `docs/02-TRD.md` section 6.1,
 * so error handling is one branch rather than a shape sniff per call site.
 * `ApiError` carries the `code` and the `field`, which is what lets the policy
 * editor underline the exact JSON path the server rejected.
 */

import type { EventEnvelope } from '@/types/generated'

const BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export interface ApiErrorBody {
  code: string
  message: string
  field?: string
  details?: unknown
}

export class ApiError extends Error {
  readonly code: string
  readonly field?: string
  readonly status: number
  readonly details?: unknown

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.field = body.field
    this.details = body.details
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    // A network failure is not a 500 -- the distinction matters to the UI,
    // which shows "Can't reach the AgentShield API" rather than a retry loop.
    throw new ApiError(0, {
      code: 'unreachable',
      message: "Can't reach the AgentShield API.",
    })
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: ApiErrorBody } | null
    throw new ApiError(
      response.status,
      body?.error ?? { code: 'internal_error', message: response.statusText },
    )
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

interface Envelope<T> {
  data: T
}

export const api = {
  get: <T>(path: string) => request<Envelope<T>>(path).then((r) => r.data),
  post: <T>(path: string, body?: unknown) =>
    request<Envelope<T>>(path, { method: 'POST', body: JSON.stringify(body ?? {}) }).then(
      (r) => r.data,
    ),
  patch: <T>(path: string, body?: unknown) =>
    request<Envelope<T>>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) }).then(
      (r) => r.data,
    ),
  /** For the two endpoints that return a cursor alongside `data`. */
  raw: <T>(path: string) => request<T>(path),
}

// ──────────────────────────────────────────────────────────────────────
// Endpoint helpers
// ──────────────────────────────────────────────────────────────────────

export interface RunSummary {
  id: string
  seed: number
  employee_count: number
  speed: number
  scenario: string
  status: string
  sim_ts: number
  sim_day: number
  created_at: string
}

export interface EmployeePublic {
  id: string
  name: string
  role: string
  team: string
  agent_brand: string
  sprite_key: string
  desk: [number, number]
  desk_slot: string
  manager_id: string | null
  daily_budget_usd: number
  status: string
  current_task_id: string | null
  risk_score: number
  risk_confidence: 'low' | 'normal'
  today: {
    requests: number
    tokens: number
    cost_usd: number
    allowed: number
    blocked: number
    review: number
    redacted: number
  }
}

export interface RiskFactor {
  feature: string
  value: number
  z: number
  contribution: number
  explanation: string
}

export interface RiskProfile {
  employee_id: string
  score: number
  static: number
  behavioural: number
  ml: number
  confidence: 'low' | 'normal'
  top_factors: RiskFactor[]
  features: Record<string, number>
  sessions_observed: number
}

export interface ApprovalCard {
  approval: {
    id: string
    task_id: string
    status: string
    reason: string
    policy_id: string
    risk_at_request: number
    cost_so_far_usd: number
    requested_sim_ts: number
    expires_sim_ts: number
    note: string | null
  }
  requester: {
    id: string
    name: string
    role: string
    team: string
    risk_score: number
    sprite_key: string
  }
  action: {
    tool: string
    target_resource: string
    environment: string
    args_preview: string
  }
  context: {
    reason: string
    policy_id: string
    cost_so_far_usd: number
    session_actions: number
    requester_7d_rate_for_tool: number
  }
}

export interface Policy {
  id: string
  version: number
  name: string
  gate: number
  priority: number
  effect: 'allow' | 'redact' | 'review' | 'block'
  enabled: boolean
  is_draft: boolean
  when: Record<string, unknown>
  approver: { role: string; scope: string } | null
  ttl_sim_seconds: number
  route_override: string | null
  message: string
  match_count_24h?: number
}

export interface OfficeSnapshot {
  run_id: string
  seq: number
  sim_ts: number
  speed: number
  avatars: AvatarState[]
  pending_approvals: number
}

export interface AvatarState {
  employee_id: string
  sprite_key: string
  tile: { x: number; y: number }
  facing: 'n' | 'e' | 's' | 'w'
  fsm: 'idle' | 'walking' | 'working' | 'waiting' | 'blocked' | 'meeting'
  badge: 'none' | 'working' | 'waiting' | 'blocked' | 'anomaly'
  name: string
  role: string
  team: string
  risk_score: number
  status: string
  current_task_title: string | null
}

export interface MetricsSummary {
  employees_enabled: number
  requests_today: number
  spend_today_usd: number
  waste_prevented_usd: number
  blocked_actions: number
  approvals_today: number
  high_risk_sessions: number
  open_incidents: number
  spend_by_team: { team: string; usd: number }[]
  risk_by_team: { team: string; level: string; score: number; drivers: string[] }[]
  trend_7d: { sim_date: string; spend_usd: number; blocked: number; approvals: number }[]
  why_high: { team: string | null; reasons: string[] }
}

export interface Incident {
  id: string
  employee_id: string
  detector: string
  score: number
  opened_sim_ts: number
  last_seen_sim_ts: number
  status: string
  summary: string
  evidence: { event_seq: number; sim_ts: number; kind: string; detail: string }[]
}

export const endpoints = {
  runs: () => api.get<RunSummary[]>('/sim/runs'),
  run: (id: string) => api.get<RunSummary>(`/sim/runs/${id}`),
  createRun: (body: Record<string, unknown>) =>
    api.post<{ run_id: string; employees: EmployeePublic[] }>('/sim/runs', body),
  control: (id: string, body: Record<string, unknown>) =>
    api.post<{ status: string; speed: number; sim_ts: number }>(
      `/sim/runs/${id}/control`,
      body,
    ),
  advance: (id: string, body: Record<string, unknown>) =>
    api.post<Record<string, number>>(`/sim/runs/${id}/advance`, body),
  snapshot: (id: string) => api.get<OfficeSnapshot>(`/sim/runs/${id}/state`),

  employees: (runId: string, team?: string) =>
    api.get<EmployeePublic[]>(
      `/employees?run_id=${runId}${team ? `&team=${team}` : ''}`,
    ),
  employee: (runId: string, id: string) =>
    api.get<{
      employee: EmployeePublic
      risk: RiskProfile | null
      current_task: { id: string; title: string; repo: string; environment: string } | null
      recent_decisions: {
        seq: number
        sim_ts: number
        kind: string
        tool?: string
        resource?: string
        decision?: string
        task_id: string | null
      }[]
      seven_day: { requests: number; tokens: number; cost_usd: number }
    }>(`/employees/${id}?run_id=${runId}`),

  events: (runId: string, sinceSeq = 0, limit = 200) =>
    api.raw<{ data: EventEnvelope[]; next_seq: number; has_more: boolean }>(
      `/events?run_id=${runId}&since_seq=${sinceSeq}&limit=${limit}`,
    ),
  task: (id: string) =>
    api.get<{
      task: Record<string, unknown>
      gate1: Record<string, unknown> | null
      actions: Record<string, unknown>[]
      approvals: Record<string, unknown>[]
    }>(`/tasks/${id}`),

  approvals: (runId: string, status = 'pending') =>
    api.get<ApprovalCard[]>(`/approvals?run_id=${runId}&status=${status}`),
  decide: (runId: string, approvalId: string, body: Record<string, unknown>) =>
    api.post<{ status: string; task_status: string }>(
      `/approvals/${approvalId}/decide?run_id=${runId}`,
      body,
    ),

  policies: (runId?: string, includeDrafts = true) =>
    api.get<Policy[]>(
      `/policies?include_drafts=${includeDrafts}${runId ? `&run_id=${runId}` : ''}`,
    ),
  togglePolicy: (id: string, enabled: boolean) =>
    api.post<Policy>(`/policies/${id}/toggle`, { enabled }),
  createPolicy: (body: Record<string, unknown>) => api.post<Policy>('/policies', body),
  patchPolicy: (id: string, body: Record<string, unknown>) =>
    api.patch<Policy>(`/policies/${id}`, body),
  promotePolicy: (body: Record<string, unknown>) =>
    api.post<Policy>('/policy-lab/promote', body),
  validatePolicy: (when: unknown, gate: number) =>
    api.post<{ valid: boolean; fields_used: string[] }>('/policies/validate', { when, gate }),
  policyFields: () =>
    api.get<{
      gate1: string[]
      gate2: string[]
      operators: string[]
      combinators: string[]
    }>('/policies/fields'),
  simulatePolicy: (body: Record<string, unknown>) =>
    api.post<Record<string, unknown>>('/policy-lab/simulate', body),

  riskLeaderboard: (runId: string, team?: string) =>
    api.get<RiskProfile[]>(`/risk/employees?run_id=${runId}${team ? `&team=${team}` : ''}`),
  explainRisk: (runId: string, id: string) =>
    api.get<
      RiskProfile & {
        baseline: { feature: string; mean: number; std: number; current: number }[]
        recent_contributors: { event_seq: number; sim_ts: number; kind: string; detail: string }[]
      }
    >(`/risk/employees/${id}/explain?run_id=${runId}`),
  incidents: (runId: string, status = 'open') =>
    api.get<Incident[]>(`/incidents?run_id=${runId}&status=${status}`),
  acknowledgeIncident: (runId: string, id: string) =>
    api.post<Incident>(`/incidents/${id}/acknowledge?run_id=${runId}`),

  metrics: (runId: string, scope = 'exec') =>
    api.get<MetricsSummary>(`/metrics/summary?run_id=${runId}&scope=${scope}`),
  spend: (runId: string, groupBy = 'team', days = 7) =>
    api.get<{
      group_by: string
      days: number
      series: { key: string; usd: number; tokens: number; waste_usd: number }[]
    }>(`/metrics/spend?run_id=${runId}&group_by=${groupBy}&days=${days}`),
}
