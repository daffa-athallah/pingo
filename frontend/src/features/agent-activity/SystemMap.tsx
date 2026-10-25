import { AGENTS, AgentIcon, EventSourceIcon } from './agentMeta'
import type { AgentKey } from './agentMeta'
import { buildMapView, EDGE_PATHS, NODES, VIEW } from './mapModel'
import type { EdgeId, EdgeUse, MapNodeId, MapNodeSpec, NodeView } from './mapModel'
import type { Timeline } from './traceAdapter'

interface Props {
  timeline: Timeline
  visibleCount: number
  /** Timeline node whose step is highlighted. */
  focusKey: string | null
  /** True while playing or when the viewer picked a step: its wires animate. */
  animateFocus: boolean
  onSelectNode: (id: MapNodeId) => void
}

const DIRECTIONAL = new Set<EdgeId>(['in-ev', 'event-ctx', 'ctx-cr', 'cr-out', 'cr-ol', 'ctx-ver'])
const ICON: Partial<Record<MapNodeId, AgentKey>> = { evidence: 'EVIDENCE', openloop: 'OPEN_LOOP', context: 'CONTEXT', critic: 'CRITIC', verifier: 'VERIFIER', zetaris: 'ZETARIS', shot: 'SOURCE', output: 'RESULT' }

function wrap(text: string, max = 15): string[] {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(' ')) {
    if (line && `${line} ${word}`.length > max) { lines.push(line); line = word } else line = line ? `${line} ${word}` : word
  }
  if (line) lines.push(line)
  return lines.slice(0, 2)
}

const clip = (text: string | undefined, max = 18) => (text && text.length > max ? `${text.slice(0, max - 1)}…` : text)

function Icon({ id, x, y, size = 22 }: { id: MapNodeId; x: number; y: number; size?: number }) {
  return <g transform={`translate(${x} ${y})`} className="aa-map-icon">{id === 'event' ? <EventSourceIcon size={size} /> : <AgentIcon agent={ICON[id] ?? 'OTHER'} size={size} quiet />}</g>
}

function Wire({ id, edge }: { id: EdgeId; edge: { state: 'used' | 'active'; dir: EdgeUse['dir'] } | undefined }) {
  const d = EDGE_PATHS[id]
  const state = edge?.state ?? 'idle'
  const marker = DIRECTIONAL.has(id) ? `url(#aa-map-arrow-${state})` : undefined
  return (
    <g>
      <path d={d} className={`aa-wire aa-wire-${state}${id === 'cr-ol' ? ' is-return' : ''}`} markerEnd={marker} fill="none" />
      {state === 'active' ? (
        <>
          {edge!.dir !== 'rev' ? <circle r="5" className="aa-packet" style={{ offsetPath: `path("${d}")` }} /> : null}
          {edge!.dir !== 'fwd' ? <circle r="5" className="aa-packet aa-packet-rev" style={{ offsetPath: `path("${d}")` }} /> : null}
        </>
      ) : null}
    </g>
  )
}

function Agent({ spec, view, onSelect }: { spec: MapNodeSpec; view: NodeView; onSelect: () => void }) {
  const meta = AGENTS[spec.agent ?? 'OTHER']
  const lines = wrap(view.state === 'idle' ? 'Idle' : view.state === 'active' ? `${view.text}…` : view.text)
  return (
    <g className={`aa-map-node is-${view.state}`} transform={`translate(${spec.x} ${spec.y})`} role="button" tabIndex={0} aria-label={`${meta.label}: ${view.text}`}
      onClick={onSelect} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } }}>
      <rect className="aa-map-halo" x="-6" y="-6" width={spec.w + 12} height={spec.h + 12} rx="24" />
      <rect className="aa-map-card" width={spec.w} height={spec.h} rx="18" />
      <circle className="aa-map-badge" cx="34" cy="34" r="18" />
      <Icon id={spec.id} x={23} y={23} />
      <text x="16" y="82" className="aa-map-name">{meta.label}</text>
      <text x="16" y="100" className="aa-map-role">{meta.role.toUpperCase()}</text>
      {lines.map((line, i) => <text key={line} x="16" y={122 + i * 16} className="aa-map-status">{line}</text>)}
    </g>
  )
}

function Chip({ spec, title, sub, state, onSelect }: { spec: MapNodeSpec; title: string; sub?: string; state: NodeView['state']; onSelect?: () => void }) {
  if (spec.id === 'output') {
    return (
      <g className={`aa-map-node aa-map-chip is-${state}`} transform={`translate(${spec.x} ${spec.y})`}>
        <rect className="aa-map-halo" x="-5" y="-5" width={spec.w + 10} height={spec.h + 10} rx="20" />
        <rect className="aa-map-card" width={spec.w} height={spec.h} rx="16" />
        <Icon id="output" x={spec.w / 2 - 11} y={14} />
        <text x={spec.w / 2} y={62} textAnchor="middle" className="aa-map-name aa-map-name-sm">{title}</text>
      </g>
    )
  }
  return (
    <g className={`aa-map-node aa-map-chip is-${state}`} transform={`translate(${spec.x} ${spec.y})`} role={onSelect ? 'button' : undefined} tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect} onKeyDown={onSelect ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() } } : undefined}>
      <rect className="aa-map-halo" x="-5" y="-5" width={spec.w + 10} height={spec.h + 10} rx="20" />
      <rect className="aa-map-card" width={spec.w} height={spec.h} rx="16" />
      <Icon id={spec.id} x={14} y={spec.h / 2 - 11} size={22} />
      <text x="46" y={sub ? spec.h / 2 - 3 : spec.h / 2 + 5} className="aa-map-name aa-map-name-sm">{title}</text>
      {sub ? <text x="46" y={spec.h / 2 + 15} className="aa-map-status">{sub}</text> : null}
    </g>
  )
}

export default function SystemMap({ timeline, visibleCount, focusKey, animateFocus, onSelectNode }: Props) {
  const view = buildMapView(timeline, visibleCount, focusKey, animateFocus)
  const spec = (id: MapNodeId) => NODES.find((n) => n.id === id)!
  const detail = (title: string) => timeline.nodes.find((n) => n.kind === 'input' && n.title === title)?.detail
  const agents: MapNodeId[] = ['evidence', 'openloop', 'context', 'critic']
  const z = view.nodes.zetaris
  const ns = view.nodes.nightshift
  const providers = [['openai', 'OpenAI'], ['nvidia', 'NVIDIA']] as const

  return (
    <figure className="aa-map" aria-label="Live system map">
      <svg viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} role="img" aria-label="How Recall's agents, shared state and model routing connect">
        <defs>
          {(['idle', 'used', 'active'] as const).map((s) => (
            <marker key={s} id={`aa-map-arrow-${s}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M1 1.5 8.5 5 1 8.5Z" className={`aa-map-arrow aa-map-arrow-${s}`} />
            </marker>
          ))}
        </defs>

        {/* Recall boundary */}
        <rect className="aa-map-boundary" x="186" y="82" width="712" height="342" rx="28" />
        <text x="884" y="104" textAnchor="end" className="aa-map-boundary-label">RECALL</text>

        {(Object.keys(EDGE_PATHS) as EdgeId[]).map((id) => <Wire key={id} id={id} edge={view.edges[id]} />)}

        <g className={`aa-map-node aa-map-bar aa-map-zetaris is-${z.state}`} transform={`translate(${spec('zetaris').x} ${spec('zetaris').y})`} role="button" tabIndex={0}
          onClick={() => onSelectNode('zetaris')} onKeyDown={(e) => { if (e.key === 'Enter') onSelectNode('zetaris') }}>
          <rect className="aa-map-halo" x="-5" y="-5" width="710" height="62" rx="20" />
          <rect className="aa-map-card" width="700" height="52" rx="16" />
          <Icon id="zetaris" x={16} y={15} />
          <text x="52" y="22" className="aa-map-name aa-map-name-sm">ZETARIS · Shared state</text>
          <text x="52" y="40" className="aa-map-status">Evidence, entities and loops move between agents through shared state</text>
          <g transform="translate(538 14)"><rect width="148" height="24" rx="12" className="aa-map-pending" /><text x="74" y="16" textAnchor="middle" className="aa-map-pending-text">Integration pending</text></g>
        </g>

        <g className={`aa-map-node aa-map-bar is-${ns.state}`} transform={`translate(${spec('nightshift').x} ${spec('nightshift').y})`}>
          <rect className="aa-map-halo" x="-5" y="-5" width="710" height="66" rx="20" />
          <rect className="aa-map-card" width="700" height="56" rx="16" />
          <text x="20" y="25" className="aa-map-name aa-map-name-sm">METERLESS NIGHTSHIFT</text>
          <text x="20" y="43" className="aa-map-status">Model routing. No agent calls a model directly.</text>
          <text x="680" y="25" textAnchor="end" className="aa-map-routing">{view.routing ? 'requested → routed' : ''}</text>
          <text x="680" y="43" textAnchor="end" className="aa-map-status aa-map-routing-value">{view.routing ?? ''}</text>
        </g>

        <Chip spec={spec('shot')} title="Screenshot" sub={clip(detail('Screenshot'), 21) ?? 'Input'} state={view.nodes.shot.state} onSelect={() => onSelectNode('shot')} />
        <Chip spec={spec('event')} title="Context event" sub={clip(detail('Calendar event') ?? detail('Context event'), 21) ?? 'Input'} state={view.nodes.event.state} onSelect={() => onSelectNode('event')} />
        {agents.map((id) => <Agent key={id} spec={spec(id)} view={view.nodes[id]} onSelect={() => onSelectNode(id)} />)}
        <Chip spec={spec('verifier')} title="Verifier" state={view.nodes.verifier.state} onSelect={() => onSelectNode('verifier')} />
        <Chip spec={spec('output')} title={view.outputLabel} state={view.nodes.output.state} onSelect={() => onSelectNode('output')} />
        {providers.map(([id, name]) => (
          <Chip key={id} spec={spec(id)} title={name} sub={view.provider[id] ?? 'Provider'} state={view.edges[id === 'openai' ? 'ns-openai' : 'ns-nvidia']?.state === 'active' ? 'active' : view.provider[id] ? 'done' : 'idle'} />
        ))}
      </svg>
      <figcaption className="aa-map-caption" aria-live="polite">
        {view.caption ? (
          <>
            <strong>{view.caption.agent.replace('_', ' ')} · {view.caption.action.replace('_', ' ')}</strong>
            <span>{view.caption.reason}</span>
          </>
        ) : <span>Waiting for the first step…</span>}
      </figcaption>
    </figure>
  )
}
