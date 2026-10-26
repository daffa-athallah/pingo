import type { ReactElement } from 'react'
import type { Receipt } from './types'

export type AgentKey = 'SOURCE' | 'EVIDENCE' | 'ZETARIS' | 'OPEN_LOOP' | 'CONTEXT' | 'VERIFIER' | 'CRITIC' | 'RESULT' | 'OTHER'

export interface AgentMeta {
  label: string
  role: string
  question: string
}

export const AGENTS: Record<AgentKey, AgentMeta> = {
  SOURCE: { label: 'Input', role: 'Input', question: 'What triggered this run?' },
  EVIDENCE: { label: 'Evidence', role: 'Perception', question: 'What am I looking at?' },
  ZETARIS: { label: 'Zetaris', role: 'Shared state', question: 'What does Recall already know?' },
  OPEN_LOOP: { label: 'Open Loop', role: 'Intention', question: 'What is this person still trying to do?' },
  CONTEXT: { label: 'Context', role: 'Relevance', question: 'Does something happening now make this relevant?' },
  VERIFIER: { label: 'Verifier', role: 'Verification', question: 'Is this context actually true right now?' },
  CRITIC: { label: 'Critic', role: 'Judgment', question: 'Is this actually worth bothering the user about?' },
  RESULT: { label: 'Result', role: 'Outcome', question: 'What did Recall decide?' },
  OTHER: { label: 'Step', role: 'Step', question: '' },
}

/** Position in the architecture. A hop to a lower rank is a return, e.g. Critic → Open Loop. */
export const RANK: Record<AgentKey, number> = {
  SOURCE: 0, EVIDENCE: 1, ZETARIS: 2, OPEN_LOOP: 3, CONTEXT: 4, VERIFIER: 4.5, CRITIC: 5, RESULT: 6, OTHER: -1,
}

export function agentKey(agent: string): AgentKey {
  switch (agent) {
    case 'EVIDENCE': return 'EVIDENCE'
    case 'INGESTION': case 'ZETARIS': case 'REPOSITORY': return 'ZETARIS'
    case 'UPLOAD': return 'SOURCE'
    case 'OPEN_LOOP': return 'OPEN_LOOP'
    case 'CONTEXT': return 'CONTEXT'
    case 'VERIFIER': return 'VERIFIER'
    case 'CRITIC': return 'CRITIC'
    default: return 'OTHER'
  }
}

/** Trace events with agent INGESTION come from the in-memory repository, not a real Zetaris call yet. */
export const isZetarisPlaceholder = (agent: string) => agent === 'INGESTION'

const NEXT_LABELS: Record<string, string> = {
  INGESTION: 'Zetaris', OPEN_LOOP: 'Open Loop', CONTEXT: 'Context', CRITIC: 'Critic', VERIFIER: 'Context verifier',
  OUTPUT: 'Output', CHECK_IN: 'Check-in', STOP: 'End of run', ZETARIS: 'Zetaris', REPOSITORY: 'Demo workspace', EVIDENCE: 'Evidence', STATE: 'Loop state',
}
export const nextLabel = (next: string | null) => (next ? NEXT_LABELS[next] ?? next : null)

const PROVIDERS: Record<string, string> = { nvidia: 'NVIDIA', openai: 'OpenAI', google: 'Google', anthropic: 'Anthropic' }
export const providerLabel = (provider: string | null) => (provider ? PROVIDERS[provider] ?? provider : null)

export function modelLabel(id: string | null): string | null {
  if (!id) return null
  const known: Array<[RegExp, string]> = [
    [/nemotron-3-ultra/, 'Nemotron 3 Ultra'],
    [/nemotron-3\.5-lightning/, 'Nemotron 3.5 Lightning'],
    [/nemotron-3-super/, 'Nemotron 3 Super'],
    [/^gpt-4o-mini/, 'GPT-4o mini'],
    [/^gpt-4o/, 'GPT-4o'],
    [/^gemini-([\d.]+)-flash-lite/, 'Gemini Flash Lite'],
  ]
  for (const [pattern, label] of known) if (pattern.test(id)) return label
  return id.split('/').pop() ?? id
}

export function receiptSummary(receipt: Receipt | null) {
  if (!receipt) return null
  return {
    requested: modelLabel(receipt.requested_model),
    routed: modelLabel(receipt.routed_model),
    provider: providerLabel(receipt.provider),
    rawRequested: receipt.requested_model,
    rawRouted: receipt.routed_model,
  }
}

const base = { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true } as const

export function AgentIcon({ agent, size = 20, quiet = false }: { agent: AgentKey; size?: number; quiet?: boolean }): ReactElement {
  const props = { ...base, width: size, height: size }
  switch (agent) {
    case 'EVIDENCE':
      return <svg {...props}><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="3" /></svg>
    case 'OPEN_LOOP':
      return <svg {...props}><path d="M20 12a8 8 0 1 1-2.6-5.9" /><path d="M20 4v4.5h-4.5" /><circle cx="12" cy="12" r="2.2" /></svg>
    case 'CONTEXT':
      return <svg {...props}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.8 2.6 4 5.6 4 9s-1.2 6.4-4 9c-2.8-2.6-4-5.6-4-9s1.2-6.4 4-9Z" /></svg>
    case 'CRITIC':
      return <svg {...props}><path d="M12 3v18M7 21h10" /><path d="M5 6.5h14" /><path d="m5 6.5-3 7a3 3 0 0 0 6 0Zm14 0-3 7a3 3 0 0 0 6 0Z" /></svg>
    case 'ZETARIS':
      return <svg {...props}><ellipse cx="12" cy="6" rx="7.5" ry="3" /><path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6M4.5 12v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-6" /></svg>
    case 'VERIFIER':
      return <svg {...props}><path d="M12 3 4.5 6v5.5c0 4.6 3.1 8 7.5 9.5 4.4-1.5 7.5-4.9 7.5-9.5V6Z" /><path d="m8.8 12 2.2 2.2 4.2-4.4" /></svg>
    case 'SOURCE':
      return <svg {...props}><rect x="6" y="2.5" width="12" height="19" rx="3" /><path d="M10 18.5h4" /></svg>
    case 'RESULT':
      if (quiet) return <svg {...props}><circle cx="12" cy="12" r="9" /><path d="m8.5 12.3 2.4 2.4 4.6-5" /></svg>
      return <svg {...props}><path d="M6 9a6 6 0 1 1 12 0c0 6 2.5 7.5 2.5 7.5h-17S6 15 6 9Z" /><path d="M10 20a2 2 0 0 0 4 0" /></svg>
    default:
      return <svg {...props}><circle cx="12" cy="12" r="3" /></svg>
  }
}

export const EventSourceIcon = ({ size = 20 }: { size?: number }) => (
  <svg {...base} width={size} height={size}><rect x="3.5" y="5" width="17" height="15.5" rx="3" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
)
