// Shared FastAPI base URL. The Check-in adapter lives in pages/checkin/checkInService.ts.
// Set VITE_API_BASE_URL in .env.local when the backend is ready.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

import type { RecallCategory, RecallEntity } from '../types/recall'

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

export function getIntegrationStatus(signal?: AbortSignal): Promise<{
  repository: string; mode: string; status: string;
  real_roundtrip_verified: boolean; real_orchestrator_verified: boolean;
}> {
  return get('/integration-status', signal)
}
