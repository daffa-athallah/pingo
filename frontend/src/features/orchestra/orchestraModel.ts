import type { Receipt, TraceEvent } from '../agent-activity/types'
import { modelLabel } from '../agent-activity/agentMeta'
import type { RunRecord } from '../../services/runsApi'

export type AgentId = 'evidence' | 'openloop' | 'context' | 'critic'
export const AGENT_IDS: AgentId[] = ['evidence', 'openloop', 'context', 'critic']

const OF: Record<string, AgentId> = { EVIDENCE: 'evidence', OPEN_LOOP: 'openloop', CONTEXT: 'context', VERIFIER: 'context', CRITIC: 'critic' }
const DECISIONS = new Set(['CREATE', 'ATTACH', 'REVISE', 'RESOLVE', 'IGNORE', 'LEAVE_UNRESOLVED', 'MATCH', 'NO_MATCH', 'SURFACE', 'STAY_SILENT', 'ASK', 'REQUEST_REVISION', 'VERIFY_CONTEXT', 'EXTRACT'])

export type Row = 'evidence' | 'entities' | 'loops'
export interface Frame {
  active: AgentId | null
  done: AgentId[]
  /** Which agents take part in this run at all; the others rest. */
  involved: AgentId[]
  lit: Row[]
  /** The model that answered this step, from the real receipt only. */
  model: { label: string; provider: string | null } | null
  hmem: 'idle' | 'query' | 'store' | 'unavailable'
  revision: boolean
  signals: ('location' | 'calendar' | 'time')[]
  failed: boolean
  finished: boolean
  event: TraceEvent | null
}

const SAFE = new Set(['FAILED', 'FAILED_SAFE'])

export function involvedAgents(events: TraceEvent[]): AgentId[] {
  return AGENT_IDS.filter((id) => events.some((e) => OF[e.agent] === id))
}

/** What the orchestra shows after the first `count` events of a run have happened. Everything is derived from those events; nothing is invented. */
export function frameAt(run: RunRecord, count: number): Frame {
  const events = run.result.trace_events
  const seen = events.slice(0, count)
  const last = seen[seen.length - 1] ?? null
  const done = new Set<AgentId>()
  const lit = new Set<Row>()
  let hmem: Frame['hmem'] = 'idle'
  let revision = false
  for (const e of seen) {
    const id = OF[e.agent]
    if (id && (DECISIONS.has(e.action) || e.action === 'STATE')) done.add(id)
    if (e.agent === 'REPOSITORY' || e.agent === 'ZETARIS') { if (e.action === 'STORE') { lit.add('evidence'); lit.add('entities') } else lit.add('entities') }
    if (e.agent === 'OPEN_LOOP' && (e.action === 'RETRIEVE' || e.action === 'STATE')) lit.add('loops')
    if (e.agent === 'CONTEXT' || e.agent === 'CRITIC') lit.add('loops')
    if (e.agent === 'H-MEM') hmem = e.action === 'QUERY' ? 'query' : e.action === 'STORE' ? 'store' : 'unavailable'
    if (e.action === 'REQUEST_REVISION') revision = true
  }
  const receipt: Receipt | null = last?.receipt ?? null
  const label = receipt ? modelLabel(receipt.routed_model) ?? receipt.routed_model : null
  const finished = count >= events.length && run.status !== 'running'
  const active = !finished && last && OF[last.agent] ? OF[last.agent] : null
  const kinds = [...(run.context_events ?? []), ...(run.context_event ? [{ context_type: (run.context_event as { context_type?: string }).context_type ?? 'CALENDAR' }] : [])]
  const signals = new Set<'location' | 'calendar' | 'time'>()
  if (events.some((e) => e.agent === 'CONTEXT')) {
    for (const k of kinds) {
      const t = String((k as { context_type?: string }).context_type ?? 'CALENDAR').toUpperCase()
      signals.add(t === 'LOCATION' ? 'location' : t === 'TIME' ? 'time' : 'calendar')
    }
    if (!kinds.length) signals.add('calendar')
  }
  return {
    active, done: [...done], involved: involvedAgents(events), lit: [...lit],
    model: receipt && label ? { label, provider: receipt.provider } : null,
    hmem, revision: revision && !finished, signals: [...signals],
    failed: run.status === 'failed' || events.some((e) => SAFE.has(e.action)), finished, event: last,
  }
}

const VERB: Record<AgentId, [string, string]> = {
  evidence: ['Evidence Agent is looking…', 'Extracting what is visible in your screenshot.'],
  openloop: ['Open Loop Agent is thinking…', 'Deciding what this means for your saved intentions.'],
  context: ['Context Agent is checking…', 'Asking whether something happening now makes a saved intention relevant.'],
  critic: ['Critic is deciding…', 'Judging whether this is worth a ping.'],
}
const ENDINGS: Record<string, [string, string]> = {
  STORED: ['Pingo is ready!', 'Saved. Tap to see the full reasoning trace.'],
  SURFACE: ['Worth a ping', 'Pingo surfaced a reminder. Tap to see why.'],
  STAY_SILENT: ['Pingo stayed quiet', 'Nothing here was worth interrupting you for. Tap to see why.'],
  ASK: ['Pingo has a question', 'It needs your answer before deciding. Tap to see why.'],
  FAILED_SAFE: ['Pingo stopped safely', 'Something could not finish, so nothing was sent. Tap to see what happened.'],
}

export function caption(run: RunRecord | undefined, frame: Frame | null): { title: string; subtitle: string; progress: number } {
  if (!run || !frame) return { title: 'Waiting for a run', subtitle: 'Sync a screenshot from Home, or open a saved run.', progress: 0 }
  const total = Math.max(run.result.trace_events.length, 1)
  const progress = frame.finished ? 1 : Math.min(1, (run.result.trace_events.indexOf(frame.event as TraceEvent) + 1) / total)
  if (frame.finished) {
    const [title, subtitle] = ENDINGS[run.result.final_action ?? (run.status === 'failed' ? 'FAILED_SAFE' : 'STORED')] ?? ENDINGS.STORED
    return { title, subtitle, progress: 1 }
  }
  if (frame.active) return { title: VERB[frame.active][0], subtitle: VERB[frame.active][1], progress }
  return { title: 'Pingo is working…', subtitle: frame.event?.reason ?? '', progress }
}
