/**
 * The one place risk colour is decided.
 *
 * `docs/04-UI-UX-BRIEF.md` section 5.6. The risk meter, the leaderboard, the
 * employee drawer and the office's anomaly overlay all call this -- so a score
 * of 71 is never amber on one screen and red on another.
 */

export function riskColor(score: number): string {
  if (score >= 90) return 'var(--color-risk-90)'
  if (score >= 70) return 'var(--color-risk-70)'
  if (score >= 40) return 'var(--color-risk-40)'
  return 'var(--color-risk-0)'
}

export function riskLevel(score: number): 'low' | 'medium' | 'high' | 'critical' {
  if (score >= 90) return 'critical'
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

/**
 * The score at which the office applies the anomaly overlay, and the lower one
 * at which it clears. The gap is hysteresis: without it, an employee hovering
 * at the threshold flickers between flagged and not, which reads as a bug.
 */
export const ANOMALY_ON = 70
export const ANOMALY_OFF = 60
