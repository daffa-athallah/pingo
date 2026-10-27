import { useSyncExternalStore } from 'react'
import type { ContextEvaluation } from '../../services/api'
import type { RunRecord } from '../../services/runsApi'

/** The location check running right now, and the last one that finished, so Agent Activity can show them whenever it is opened.
 *  A check is one request to the backend: while it runs we only know that it is running (not which step); the real trace arrives with the answer. */
export interface NearbyState { checking: { place: string; distance: number; since: number } | null; last: RunRecord | null }
let state: NearbyState = { checking: null, last: null }
const listeners = new Set<() => void>()
const set = (next: Partial<NearbyState>) => { state = { ...state, ...next }; listeners.forEach((fn) => fn()) }
const subscribe = (fn: () => void) => { listeners.add(fn); return () => { listeners.delete(fn) } }
export const useNearby = () => useSyncExternalStore(subscribe, () => state)

export const startCheck = (place: string, distance: number) => set({ checking: { place, distance, since: Date.now() } })
export const failCheck = () => set({ checking: null })

/** A finished evaluation, as the run record Agent Activity already knows how to show. Real models and a real GPS fix, so provenance is live. */
export function finishCheck(evaluation: ContextEvaluation, place: string) {
  const result = evaluation.result
  if (!result) { set({ checking: null }); return }
  const events = result.trace_events
  set({ checking: null, last: {
    run_id: result.run_id, kind: 'context_evaluate', label: `Near ${place}`, provenance: 'live', workspace: 'canonical', synthetic_inputs: false,
    status: evaluation.state === 'FAILED_SAFE' ? 'failed' : 'done', started_at: events[0]?.timestamp ?? new Date().toISOString(),
    finished_at: events[events.length - 1]?.timestamp ?? null, result,
    context_events: [{ context_type: 'LOCATION', title: place, evaluated: true }],
  } as RunRecord })
}
