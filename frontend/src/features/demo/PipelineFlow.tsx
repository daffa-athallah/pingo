import type { TraceEvent } from '../agent-activity/types'

type NodeId = 'shot' | 'evidence' | 'memory' | 'openloop' | 'location' | 'zetaris' | 'context' | 'critic'
const NODES: Record<NodeId, { x: number; y: number; label: string; sub: string; kind: 'agent' | 'tool' | 'db' | 'dim' | 'input' }> = {
  shot: { x: 180, y: 28, label: 'Screenshot', sub: 'from your photos', kind: 'input' },
  evidence: { x: 100, y: 105, label: 'Evidence Agent', sub: 'reads what is visible', kind: 'agent' },
  memory: { x: 262, y: 105, label: 'H-MEM', sub: 'what do I remember?', kind: 'tool' },
  openloop: { x: 100, y: 195, label: 'Open Loop Agent', sub: 'what does it mean?', kind: 'agent' },
  location: { x: 262, y: 195, label: 'Map lookup', sub: 'where is it?', kind: 'tool' },
  zetaris: { x: 180, y: 292, label: 'Zetaris', sub: 'saved forever', kind: 'db' },
  context: { x: 82, y: 392, label: 'Context Agent', sub: 'wakes on a moment', kind: 'dim' },
  critic: { x: 278, y: 392, label: 'Critic', sub: 'decides to interrupt', kind: 'dim' },
}
const EDGES: [NodeId, NodeId][] = [['shot', 'evidence'], ['evidence', 'memory'], ['evidence', 'zetaris'], ['memory', 'openloop'], ['evidence', 'openloop'],
  ['openloop', 'location'], ['openloop', 'zetaris'], ['location', 'zetaris'], ['zetaris', 'context'], ['context', 'critic']]
const OF: Record<string, NodeId> = { UPLOAD: 'shot', EVIDENCE: 'evidence', 'H-MEM': 'memory', OPEN_LOOP: 'openloop', LOCATION: 'location', ZETARIS: 'zetaris', REPOSITORY: 'zetaris', CONTEXT: 'context', CRITIC: 'critic' }

/** The four agents and what they touch, lit up as a run's events arrive. Purely a view of the run's own events. */
export default function PipelineFlow({ events, running, done }: { events: TraceEvent[]; running: boolean; done: boolean }) {
  const seen = new Set<NodeId>()
  let active: NodeId | null = null
  for (const e of events) { const n = OF[e.agent]; if (n) { seen.add(n); active = n } }
  const state = (id: NodeId) => (running && active === id ? 'is-active' : seen.has(id) ? 'is-done' : 'is-idle')
  const live = (a: NodeId, b: NodeId) => running && (active === a || active === b) && seen.has(a) && seen.has(b)
  return <figure className="pipeline" aria-label="How the agents handle a screenshot">
    <svg viewBox="0 0 360 440" role="img" aria-label="Screenshot flows through the Evidence Agent, memory, the Open Loop Agent and a map lookup into Zetaris; the Context Agent and Critic wake later">
      {EDGES.map(([a, b]) => {
        const p = NODES[a], q = NODES[b]
        const dim = NODES[a].kind === 'dim' || NODES[b].kind === 'dim'
        return <line key={a + b} x1={p.x} y1={p.y + 16} x2={q.x} y2={q.y - 16} className={`pipe-edge${live(a, b) ? ' is-live' : ''}${dim ? ' is-dim' : ''}${seen.has(a) && seen.has(b) ? ' is-seen' : ''}`} />
      })}
      {(Object.keys(NODES) as NodeId[]).map((id) => {
        const n = NODES[id]
        return <g key={id} className={`pipe-node is-${n.kind} ${n.kind === 'dim' ? 'is-idle' : state(id)}`} transform={`translate(${n.x} ${n.y})`}>
          {n.kind === 'db'
            ? <><ellipse cx="0" cy="-12" rx="46" ry="10" /><path d="M-46 -12 V14 A46 10 0 0 0 46 14 V-12" /><ellipse cx="0" cy="14" rx="46" ry="10" className="pipe-db-base" /></>
            : <rect x="-68" y="-20" width="136" height="40" rx="12" />}
          <text y={n.kind === 'db' ? 4 : -2} textAnchor="middle" className="pipe-label">{n.label}</text>
          <text y={n.kind === 'db' ? 32 : 13} textAnchor="middle" className="pipe-sub">{n.sub}</text>
        </g>
      })}
    </svg>
    <figcaption>{done ? 'Saved. The Context Agent and Critic stay asleep until a moment (a place or a calendar event) calls them.'
      : running ? 'The agents are working on your screenshot…' : 'Pick a screenshot to watch the agents work.'}</figcaption>
  </figure>
}
