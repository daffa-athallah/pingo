// Runs and the demo workspace. Kept apart from api.ts so the product screens and this tooling do not edit the same file.
import { API_BASE_URL } from './api'
import type { Provenance, RunResult, RunStatus } from '../features/agent-activity/types'

export interface RunRecord {
  run_id: string
  kind: 'screenshot_upload' | 'context_evaluate' | 'context_critic' | 'revision_fixture' | 'scripted_sample'
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
}

export interface Health {
  status: string
  mode: 'real' | 'demo' | 'sample'
  workspace: 'canonical' | 'demo' | 'sample'
  repository: string
  demo_workspace?: { storage: string; snapshot_counts?: Record<string, number> }
}

const base = () => API_BASE_URL.replace(/\/$/, '')

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base()}${path}`, { ...init, signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000) })
  if (!response.ok) {
    let detail = ''
    try { detail = ((await response.json()) as { detail?: string }).detail ?? '' } catch { /* not JSON */ }
    throw new Error(detail || `Request failed (${response.status}).`)
  }
  return response.json() as Promise<T>
}

export const getHealth = (signal?: AbortSignal) => json<Health>('/health', { signal })
export const getRunRecords = (signal?: AbortSignal) => json<RunRecord[]>('/runs', { signal })
export const getRunRecord = (runId: string, signal?: AbortSignal) => json<RunRecord>(`/api/runs/${encodeURIComponent(runId)}`, { signal })
export const resetDemo = () => json<{ ok: boolean; evidence: number; active_loops: number }>('/api/demo/reset', { method: 'POST' })

/** Sends the raw image bytes. Returns at once with a run_id; poll getRunRecord for progress. */
export const startUpload = (file: File) =>
  json<{ run_id: string; status: RunStatus; duplicate?: boolean; outcome?: UploadOutcome }>('/api/screenshots', {
    method: 'POST', body: file, headers: { 'Content-Type': file.type || 'application/octet-stream' },
  })
