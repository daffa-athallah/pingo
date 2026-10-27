// Runs and the demo workspace. Kept apart from api.ts so the product screens and this tooling do not edit the same file.
import { API_BASE_URL } from './api'
import type { Provenance, RunResult, RunStatus } from '../features/agent-activity/types'

export interface RunRecord {
  run_id: string
  kind: 'screenshot_upload' | 'context_evaluate' | 'context_critic' | 'revision_fixture' | 'scripted_sample' | 'recorded_sample'
  label: string
  provenance: Provenance
  workspace: 'canonical' | 'demo' | 'sample'
  synthetic_inputs: boolean
  status: RunStatus
  started_at: string | null
  finished_at: string | null
  result: RunResult
  outcome?: UploadOutcome
  context_event?: { title?: string; location_name?: string; city?: string }
  context_events?: { title?: string; context_type?: string; location_name?: string; city?: string; evaluated?: boolean }[]
  check_ins?: { id: string; question: string }[]
  notification_id?: string
  cached?: boolean
  recording_note?: string
  loop_title?: string
  original_title?: string
  final_title?: string
}

export interface UploadOutcome {
  status: 'stored' | 'stored_without_loop' | 'duplicate'
  evidence: { evidence_id: string; sensitive: boolean; domain: string | null; summary: string | null; entities: { entity_id: string; name: string }[]; image_url: string | null } | null
  open_loop: {
    decision: string | null
    reason: string | null
    confidence: number | null
    loop: { loop_id: string; title: string; screenshot_count: number } | null
    change: { change: string; before: { screenshots: number } | null; after: { screenshots: number } } | null
  }
  receipts: { agent: string; action: string; receipt: { requested_model: string | null; routed_model: string | null; provider: string | null } }[]
  error: string | null
  locations?: { entity_id: string; name: string; status: string; reason: string | null; candidates?: { label: string; lat: number; lon: number; location_id: string }[]; latitude: string | null; longitude: string | null; location_id: string | null }[]
}

export interface Health {
  status: string
  mode: 'real' | 'demo' | 'sample'
  workspace: 'canonical' | 'demo' | 'sample'
  repository: string
  live_models?: boolean
  demo_workspace?: { storage: string; snapshot_counts?: Record<string, number> }
}

const base = () => API_BASE_URL.replace(/\/$/, '')

async function json<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const response = await fetch(`${base()}${path}`, { ...init, signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(timeoutMs)]) : AbortSignal.timeout(timeoutMs) })
  if (!response.ok) {
    let detail = ''
    try { detail = ((await response.json()) as { detail?: string }).detail ?? '' } catch { /* not JSON */ }
    throw new Error(detail || `Request failed (${response.status}).`)
  }
  return response.json() as Promise<T>
}

export const getHealth = (signal?: AbortSignal) => json<Health>('/health', { signal })
export const getRunRecords = (signal?: AbortSignal) => json<RunRecord[]>('/runs', { signal })
// The real backend can be busy with Zetaris for a while; a run's status is worth waiting for.
export const getRunRecord = (runId: string, signal?: AbortSignal) => json<RunRecord>(`/api/runs/${encodeURIComponent(runId)}`, { signal }, 120000)
export const resetDemo = () => json<{ ok: boolean; evidence: number; active_loops: number }>('/api/demo/reset', { method: 'POST' })

/** Sends the raw image bytes. Returns at once with a run_id; poll getRunRecord for progress. */
export const startUpload = (file: File) =>
  json<{ run_id: string; status: RunStatus; duplicate?: boolean; outcome?: UploadOutcome }>('/api/screenshots', {
    method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' },
  }, 180000)

export interface CachedRecallView {
  notification_id: string; loop_id: string; run_id: string; title: string; reason: string
  evidence_ids: string[]; captured_at: string; synthetic_inputs: boolean
  context?: { title?: string; occurs_at?: string; location_name?: string; city?: string }
}
export interface CachedHistory {
  cached_at: string; data_source: 'cached_run_history'; provenance: 'recorded'; workspace: 'sample'
  model_calls: false; agents_executed: false; records: RunRecord[]; recall_views: CachedRecallView[]
}
export const getCachedHistory = (signal?: AbortSignal) => json<CachedHistory>('/api/sample/history', { signal })

export interface SampleCase { case: string; label: string; kind: 'screenshot' | 'location' | 'review'; image_url: string | null; sensitive: boolean }
export const getSampleCases = (signal?: AbortSignal) => json<SampleCase[]>('/api/sample/cases', { signal })
export const replaySampleCase = (name: string) => json<RunRecord>(`/api/sample/cases/${encodeURIComponent(name)}/replay`, { method: 'POST' })
export const resetSample = () => json<{ ok: boolean }>('/api/sample/reset', { method: 'POST' })

export interface ZetarisProof {
  captured_at: string; source: string; namespace: string; role: string
  table_counts: Record<string, number>
  queries: { role: string; sql: string; rows_returned: number; sample: string[][]; note: string }[]
}
export const getZetarisProof = (signal?: AbortSignal) => json<ZetarisProof>('/api/sample/zetaris', { signal })

export const setEntityLocation = (entityId: string, link: string, pick?: { location_id: string; label: string }) =>
  json<{ entity_id: string; name: string; latitude: number; longitude: number; location_id: string }>(`/api/entities/${encodeURIComponent(entityId)}/location`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ link, ...(pick ? { location_id: pick.location_id, label: pick.label } : {}) }),
  })

export const deleteIntention = (loopId: string) =>
  json<{ deleted: string; title: string; screenshots_hidden: number; can_sync_again: number }>(`/api/open-loops/${encodeURIComponent(loopId)}/delete`, { method: 'POST' }, 120000)

export const findLocation = (entityId: string) =>
  json<{ entity_id: string; name: string; status: string; reason?: string; latitude?: string; longitude?: string; location_id?: string }>(
    `/api/entities/${encodeURIComponent(entityId)}/find-location`, { method: 'POST' }, 300000)

export const deleteScreenshot = (evidenceId: string) =>
  json<{ hidden: string; can_sync_again: number }>(`/api/evidence/${encodeURIComponent(evidenceId)}/delete`, { method: 'POST' }, 120000)
