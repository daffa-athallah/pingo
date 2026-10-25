import { agentKey, isZetarisPlaceholder, RANK } from './agentMeta'
import type { AgentKey } from './agentMeta'
import type { Annotations, FinalAction, RunResult, TraceEvent } from './types'

export type NodeKind = 'input' | 'state' | 'event' | 'result'
export type Lane = 'main' | 'branch'
export type EdgeKind = 'forward' | 'return' | 'resume'

export interface TimelineNode {
  key: string
  kind: NodeKind
  agent: AgentKey
  lane: Lane
  runIndex: number
  step?: number
  event?: TraceEvent
  title: string
  headline?: string
  detail?: string
  placeholder?: boolean
  /** Shown above the node when a later run continues the story. */
  breakBefore?: string
  result?: { run: RunResult }
}

export interface TimelineEdge {
  from: string
  to: string
  kind: EdgeKind
  label?: string
}

export interface Timeline {
  nodes: TimelineNode[]
  edges: TimelineEdge[]
  summary: {
    runIds: string[]
    steps: number
    revisions: number
    verifications: number
    finalAction: FinalAction
    last: RunResult
  }
}

const RETURN_LABELS: Record<string, string> = {
  REQUEST_REVISION: 'Sent back to Open Loop',
  VERIFY_CONTEXT: 'Context needs verifying',
}

function returnLabel(from: TimelineNode, to: TimelineNode): string {
  if (from.event && RETURN_LABELS[from.event.action]) return RETURN_LABELS[from.event.action]
  if (to.agent === 'CONTEXT') return 'Re-checked with verified context'
  return 'Returned for another pass'
}

/** Turns one or more RunResults (e.g. an ingestion run then a context run) into a drawable graph. */
export function buildTimeline(runs: RunResult[], annotations: Annotations = {}): Timeline {
  if (runs.length === 0) throw new Error('buildTimeline needs at least one run')
  const nodes: TimelineNode[] = []
  const edges: TimelineEdge[] = []
  let step = 0

  runs.forEach((run, runIndex) => {
    const events = run.trace_events
    const runNodes: TimelineNode[] = []
    const note = annotations.inputs?.[runIndex]
    const breakBefore = runIndex > 0 ? (run.run_type === 'CONTEXT_EVALUATION' ? 'Later, a context event arrives' : 'Next run') : undefined

    if (run.run_type === 'EVIDENCE_INGESTION') {
      const image = events[0]?.input_refs.find((ref) => ref.startsWith('image:'))?.slice(6)
      runNodes.push({ key: `r${runIndex}-input`, kind: 'input', agent: 'SOURCE', lane: 'main', runIndex, title: note?.title ?? 'Screenshot',
        detail: note?.detail ?? image, breakBefore })
    } else {
      const ids = events.flatMap((e) => e.input_refs.filter((ref) => ref.startsWith('context:')).map((ref) => ref.slice(8)))
      runNodes.push({ key: `r${runIndex}-input`, kind: 'input', agent: 'SOURCE', lane: 'main', runIndex, title: note?.title ?? 'Context event',
        detail: note?.detail ?? (ids.length ? [...new Set(ids)].join(', ') : undefined), breakBefore })
      if (!events.some((e) => agentKey(e.agent) === 'ZETARIS')) {
        runNodes.push({ key: `r${runIndex}-state`, kind: 'state', agent: 'ZETARIS', lane: 'main', runIndex, title: 'Shared state',
          detail: annotations.state?.[runIndex] ?? 'Open loops and evidence, read through the repository', placeholder: true })
      }
    }

    events.forEach((event, eventIndex) => {
      const agent = agentKey(event.agent)
      runNodes.push({ key: `r${runIndex}-e${eventIndex}`, kind: 'event', agent, lane: 'main', runIndex, step: ++step, event,
        title: event.agent, headline: annotations.headlines?.[`${runIndex}:${eventIndex}`], placeholder: isZetarisPlaceholder(event.agent) })
    })

    if (runIndex === runs.length - 1) {
      runNodes.push({ key: `r${runIndex}-result`, kind: 'result', agent: 'RESULT', lane: 'main', runIndex, title: run.final_action, result: { run } })
    }

    // Lane + edge classification: any hop to an earlier pipeline stage is a return; the branch lane lasts
    // until execution reaches (or passes) the stage it left from.
    let lane: Lane = 'main'
    let origin = 0
    let prevRank = RANK[runNodes[0].agent]
    for (let i = 1; i < runNodes.length; i += 1) {
      const prev = runNodes[i - 1]
      const node = runNodes[i]
      const rank = node.agent === 'OTHER' ? prevRank : RANK[node.agent]
      let kind: EdgeKind = 'forward'
      if (lane === 'main' && rank < prevRank) {
        lane = 'branch'
        origin = prevRank
        kind = 'return'
      } else if (lane === 'branch') {
        if (rank >= origin) { lane = 'main'; kind = 'resume' } else { kind = rank < prevRank ? 'return' : 'forward' }
      }
      node.lane = node.kind === 'result' ? 'main' : lane
      const label = kind === 'return' && prev.lane === 'main' ? returnLabel(prev, node)
        : kind === 'resume' && node.kind === 'event' ? 'Re-evaluated' : undefined
      edges.push({ from: prev.key, to: node.key, kind, label })
      prevRank = rank
    }
    nodes.push(...runNodes)
  })

  const last = runs[runs.length - 1]
  return {
    nodes,
    edges,
    summary: {
      runIds: runs.map((r) => r.run_id),
      steps: step,
      revisions: runs.reduce((n, r) => n + r.revision_count, 0),
      verifications: runs.reduce((n, r) => n + r.verification_count, 0),
      finalAction: last.final_action,
      last,
    },
  }
}

export const shortId = (id: string) => (id.length > 12 ? `${id.slice(0, 8)}…` : id)

export function refParts(ref: string): { kind: string; id: string } {
  const at = ref.indexOf(':')
  return at < 0 ? { kind: 'ref', id: ref } : { kind: ref.slice(0, at), id: ref.slice(at + 1) }
}
