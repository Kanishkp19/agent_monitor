/**
 * Props renderer — GUTTED.
 *
 * All furniture is now baked into the pre-rendered room background PNGs.
 * These stubs exist to avoid import errors in OfficeSimulation.tsx during
 * the migration. They will be removed once OfficeSimulation is updated.
 */

import type { PropItem, SimEmployee } from '../systems/Types'

 
export function buildProps(_employees: SimEmployee[]): PropItem[] {
  return []
}

export function drawProp(
   
  _c: CanvasRenderingContext2D,
   
  _p: PropItem,
   
  _now: number,
   
  _byId: Record<string, SimEmployee>,
): void {
  // no-op — furniture is in the room background images
}

