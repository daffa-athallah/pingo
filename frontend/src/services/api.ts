// Shared FastAPI base URL. The Check-in adapter lives in pages/checkin/checkInService.ts.
// Set VITE_API_BASE_URL in .env.local when the backend is ready.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

import type { RecallCategory, RecallEntity } from '../types/recall'
import type { RunResult } from '../features/agent-activity/types'

export interface EntityResponse {
  id: string
  entity_id: string
  domain: string
  name: string
  location: string | null
  screenshot_count: number
  thumbnail_ref: string | null
  inferred_intention: string | null
}

export interface OpenLoopResponse {
  loop_id: string
  title: string
  domain: string
  status: 'OPEN' | 'ACTIVE' | 'DORMANT' | 'RESOLVED' | 'INVALIDATED'
  confidence: number
  created_at: string
  updated_at: string
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(15000)
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, '')}${path}`, {
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  })
  if (!response.ok) throw new Error(`Recall data request failed (${response.status}).`)
  return response.json() as Promise<T>
}

function entityFromResponse(item: EntityResponse): RecallEntity {
  if (!['food', 'shopping', 'travel'].includes(item.domain)) throw new Error('Entity domain is not supported by this frontend route.')
  return { id: item.id, category: item.domain as RecallCategory, name: item.name,
    location: item.location ?? undefined, screenshotCount: item.screenshot_count,
    inferredIntention: item.inferred_intention ?? '' }
}

// Daffa's page components can consume these without changing their visual design.
// Counts come from persisted evidence relationships; thumbnail_ref is not assumed to be a URL.
export async function getEntities(domain: RecallCategory, signal?: AbortSignal): Promise<RecallEntity[]> {
  return (await get<EntityResponse[]>(`/entities?domain=${encodeURIComponent(domain)}`, signal)).map(entityFromResponse)
}

export async function getEntity(id: string, signal?: AbortSignal): Promise<RecallEntity> {
  return entityFromResponse(await get<EntityResponse>(`/entities/${encodeURIComponent(id)}`, signal))
}

export function getOpenLoops(signal?: AbortSignal): Promise<OpenLoopResponse[]> {
  return get('/loops', signal)
}

export function getAgentEvents(runId: string, signal?: AbortSignal): Promise<unknown[]> {
  return get(`/agent-events/${encodeURIComponent(runId)}`, signal)
}

export interface IntegrationStatusResponse {
  repository: string; mode: string; status: string;
  real_roundtrip_verified: boolean; real_orchestrator_verified: boolean;
  /** Live counts read from Zetaris. null outside real mode. */
  zetaris: { connected: boolean; evidence: number; entities: number; open_loops: number } | null
}

export function getIntegrationStatus(signal?: AbortSignal): Promise<IntegrationStatusResponse> {
  return get('/integration-status', signal)
}

export interface OpenLoopViewResponse {
  loop_id: string
  title: string
  domain: string
  status: OpenLoopResponse['status']
  confidence: number
  location: string | null
  entities: { entity_id: string; name: string }[]
  screenshot_count: number
  screenshots: { evidence_id: string; summary: string; timestamp: string; image_url: string }[]
}

/** Backend-served JPEG of a supporting screenshot, scaled to `width` pixels. */
export const imageUrl = (path: string, width: number) => `${API_BASE_URL.replace(/\/$/, '')}${path}?w=${width}`

export function getOpenLoopViews(signal?: AbortSignal): Promise<OpenLoopViewResponse[]> {
  return get('/open-loops', signal)
}

export interface SavedRunResponse {
  run_id: string
  kind: 'context_critic' | 'revision_fixture'
  scenario: string
  synthetic_context: boolean
  result: RunResult
  context_event?: { title?: string; occurs_at?: string; location_name?: string; city?: string }
  loop_title?: string
  original_title?: string
  final_title?: string
}

export function getRuns(signal?: AbortSignal): Promise<SavedRunResponse[]> {
  return get('/runs', signal)
}
