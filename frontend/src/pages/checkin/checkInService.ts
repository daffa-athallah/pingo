import { API_BASE_URL } from '../../services/api'
import type { CheckInQuestion, CheckInResponse } from './checkInTypes'
import { sampleQuestions } from './sampleQuestions'

export const isCheckInDemo = import.meta.env.VITE_CHECKIN_DEMO === 'true'
  || (import.meta.env.DEV && !import.meta.env.VITE_API_BASE_URL)
const storageKey = 'recall.checkin.demo.responses.v1'

function readDemoResponses(): Record<string, CheckInResponse> {
  const saved = localStorage.getItem(storageKey)
  if (!saved) return {}
  try {
    const parsed: unknown = JSON.parse(saved)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(Object.entries(parsed).filter(([, value]) => value && typeof value === 'object' && typeof value.response === 'string'))
  } catch { return {} }
}

function isQuestion(value: unknown): value is CheckInQuestion {
  if (!value || typeof value !== 'object') return false
  const q = value as Record<string, unknown>
  const option = (item: unknown) => !!item && typeof item === 'object' && typeof (item as Record<string, unknown>).value === 'string' && typeof (item as Record<string, unknown>).label === 'string'
  return typeof q.id === 'string' && typeof q.loop_id === 'string'
    && ['CONFIRM', 'CLARIFY', 'STILL_RELEVANT'].includes(String(q.type))
    && ['shopping', 'food', 'destination'].includes(String(q.domain))
    && typeof q.summary === 'string' && typeof q.question === 'string'
    && (q.context === undefined || typeof q.context === 'string')
    && Array.isArray(q.options) && q.options.every(option)
    && (q.positive === undefined || option(q.positive)) && (q.negative === undefined || option(q.negative))
    && Array.isArray(q.supporting_images) && q.supporting_images.every(image => image && typeof image.url === 'string' && typeof image.alt === 'string')
}

async function request(path: string, init?: RequestInit) {
  const timeout = AbortSignal.timeout(15000)
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, '')}${path}`, { ...init, signal: init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout })
  if (!response.ok) throw new Error('Check-in request failed')
  return response
}

export async function getCheckIns(signal: AbortSignal): Promise<CheckInQuestion[]> {
  if (isCheckInDemo) {
    const saved = readDemoResponses()
    return sampleQuestions.filter(question => !saved[question.id])
  }
  const response = await request('/api/check-ins', { signal })
  const data: unknown = await response.json()
  if (!data || typeof data !== 'object' || !('questions' in data) || !Array.isArray(data.questions) || !data.questions.every(isQuestion)) throw new Error('Invalid check-in data')
  const questions = data.questions as CheckInQuestion[]
  if (new Set(questions.map(question => question.id)).size !== questions.length) throw new Error('Duplicate check-in IDs')
  return questions
}

export async function respondToCheckIn(id: string, answer: CheckInResponse): Promise<void> {
  if (isCheckInDemo) {
    localStorage.setItem(storageKey, JSON.stringify({ ...readDemoResponses(), [id]: answer }))
    return
  }
  await request(`/api/check-ins/${encodeURIComponent(id)}/respond`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(answer),
  })
}
