import { modelLabel } from './agentMeta'
import type { AgentKey } from './agentMeta'
import type { Timeline, TimelineNode } from './traceAdapter'

export type MapNodeId = 'shot' | 'event' | 'evidence' | 'openloop' | 'context' | 'critic' | 'verifier' | 'zetaris' | 'nightshift' | 'openai' | 'nvidia' | 'output'
export type EdgeId =
  | 'in-ev' | 'event-ctx' | 'ctx-cr' | 'cr-out' | 'cr-ol' | 'ctx-ver'
  | 'z-ev' | 'z-ol' | 'z-ctx' | 'z-cr' | 'ns-ev' | 'ns-ol' | 'ns-ctx' | 'ns-cr' | 'ns-openai' | 'ns-nvidia'

export const VIEW = { width: 1030, height: 640 }

const AGENT_X: Record<'evidence' | 'openloop' | 'context' | 'critic', number> = { evidence: 200, openloop: 380, context: 560, critic: 740 }
const CARD = { w: 140, y: 196, h: 150 }
const cx = (id: keyof typeof AGENT_X) => AGENT_X[id] + CARD.w / 2

export interface MapNodeSpec { id: MapNodeId; x: number; y: number; w: number; h: number; agent?: AgentKey }

export const NODES: MapNodeSpec[] = [
  { id: 'event', x: 10, y: 78, w: 170, h: 66 },
  { id: 'shot', x: 10, y: 232, w: 170, h: 66 },
  { id: 'zetaris', x: 190, y: 12, w: 700, h: 52, agent: 'ZETARIS' },
  { id: 'evidence', x: AGENT_X.evidence, y: CARD.y, w: CARD.w, h: CARD.h, agent: 'EVIDENCE' },
  { id: 'openloop', x: AGENT_X.openloop, y: CARD.y, w: CARD.w, h: CARD.h, agent: 'OPEN_LOOP' },
  { id: 'context', x: AGENT_X.context, y: CARD.y, w: CARD.w, h: CARD.h, agent: 'CONTEXT' },
  { id: 'critic', x: AGENT_X.critic, y: CARD.y, w: CARD.w, h: CARD.h, agent: 'CRITIC' },
  { id: 'verifier', x: 702, y: 364, w: 104, h: 38, agent: 'VERIFIER' },
  { id: 'output', x: 928, y: 224, w: 92, h: 82 },
  { id: 'nightshift', x: 190, y: 436, w: 700, h: 56 },
  { id: 'openai', x: 330, y: 556, w: 170, h: 64 },
  { id: 'nvidia', x: 590, y: 556, w: 200, h: 64 },
]

const r = (n: number) => Math.round(n)
function elbow(points: Array<[number, number]>, radius = 12): string {
  // Polyline with rounded corners.
  let d = `M${points[0][0]} ${points[0][1]}`
  for (let i = 1; i < points.length - 1; i += 1) {
    const [x0, y0] = points[i - 1]
    const [x1, y1] = points[i]
    const [x2, y2] = points[i + 1]
    const l1 = Math.hypot(x1 - x0, y1 - y0)
    const l2 = Math.hypot(x2 - x1, y2 - y1)
    const rr = Math.min(radius, l1 / 2, l2 / 2)
    const ax = x1 - ((x1 - x0) / l1) * rr, ay = y1 - ((y1 - y0) / l1) * rr
    const bx = x1 + ((x2 - x1) / l2) * rr, by = y1 + ((y2 - y1) / l2) * rr
    d += ` L${r(ax)} ${r(ay)} Q${x1} ${y1} ${r(bx)} ${r(by)}`
  }
  const last = points[points.length - 1]
  return `${d} L${last[0]} ${last[1]}`
}

const ZB = 64 // bottom of the Zetaris bar
const NS = 436 // top of the Nightshift bar
const bottom = CARD.y + CARD.h

export const EDGE_PATHS: Record<EdgeId, string> = {
  'in-ev': 'M180 265 H200',
  'event-ctx': elbow([[180, 111], [cx('context') + 18, 111], [cx('context') + 18, CARD.y]]),
  'ctx-cr': 'M700 265 H740',
  'cr-out': 'M880 265 H928',
  'cr-ol': elbow([[cx('critic') + 22, CARD.y], [cx('critic') + 22, 150], [cx('openloop') + 22, 150], [cx('openloop') + 22, CARD.y]]),
  'ctx-ver': elbow([[cx('context') + 36, bottom], [cx('context') + 36, 383], [702, 383]]),
  'z-ev': `M${cx('evidence') - 18} ${CARD.y} V${ZB}`,
  'z-ol': `M${cx('openloop') - 18} ${CARD.y} V${ZB}`,
  'z-ctx': `M${cx('context') - 18} ${CARD.y} V${ZB}`,
  'z-cr': `M${cx('critic') - 18} ${CARD.y} V${ZB}`,
  'ns-ev': `M${cx('evidence')} ${bottom} V${NS}`,
  'ns-ol': `M${cx('openloop')} ${bottom} V${NS}`,
  'ns-ctx': `M${cx('context')} ${bottom} V${NS}`,
  'ns-cr': `M${cx('critic')} ${bottom} V${NS}`,
  'ns-openai': 'M415 492 V556',
  'ns-nvidia': 'M690 492 V556',
}

export type EdgeDir = 'fwd' | 'rev' | 'both'
export interface EdgeUse { id: EdgeId; dir: EdgeDir }

const AGENT_ID: Partial<Record<AgentKey, 'evidence' | 'openloop' | 'context' | 'critic'>> = { EVIDENCE: 'evidence', OPEN_LOOP: 'openloop', CONTEXT: 'context', CRITIC: 'critic' }
const Z: Record<string, EdgeId> = { evidence: 'z-ev', openloop: 'z-ol', context: 'z-ctx', critic: 'z-cr' }
const N: Record<string, EdgeId> = { evidence: 'ns-ev', openloop: 'ns-ol', context: 'ns-ctx', critic: 'ns-cr' }

/** Which wires carry traffic for one trace step. Derived only from the event and the step before it. */
export function usesForStep(node: TimelineNode, prev: TimelineNode | undefined): EdgeUse[] {
  const uses: EdgeUse[] = []
  if (node.kind === 'input') return [{ id: node.title === 'Screenshot' ? 'in-ev' : 'event-ctx', dir: 'fwd' }]
  if (node.kind === 'state') return [{ id: 'z-ctx', dir: 'rev' }]
  if (node.kind === 'result') return [{ id: 'cr-out', dir: 'fwd' }]
  const event = node.event
  if (!event) return uses
  if (node.agent === 'ZETARIS') return [{ id: 'z-ev', dir: 'fwd' }]
  if (node.agent === 'VERIFIER') return [{ id: 'ctx-ver', dir: 'fwd' }]
  const id = AGENT_ID[node.agent]
  if (!id) return uses
  if (id === 'openloop' && prev?.agent === 'CRITIC') uses.push({ id: 'cr-ol', dir: 'fwd' })
  if (id === 'critic' && prev?.agent === 'CONTEXT') uses.push({ id: 'ctx-cr', dir: 'fwd' })
  if (id === 'critic' && event.action === 'REQUEST_REVISION') uses.push({ id: 'cr-ol', dir: 'fwd' })
  if (id === 'critic' && prev?.agent === 'OPEN_LOOP') uses.push({ id: 'cr-ol', dir: 'rev' })
  if (id === 'context' && prev?.agent === 'VERIFIER') uses.push({ id: 'ctx-ver', dir: 'rev' })
  if (id !== 'evidence') uses.push({ id: Z[id], dir: 'both' })
  const receipt = event.receipt
  if (receipt) {
    uses.push({ id: N[id], dir: 'both' })
    if (receipt.provider === 'openai') uses.push({ id: 'ns-openai', dir: 'both' })
    if (receipt.provider === 'nvidia') uses.push({ id: 'ns-nvidia', dir: 'both' })
  }
  return uses
}

const NODE_FOR_AGENT: Partial<Record<AgentKey, MapNodeId>> = { EVIDENCE: 'evidence', OPEN_LOOP: 'openloop', CONTEXT: 'context', CRITIC: 'critic', VERIFIER: 'verifier', ZETARIS: 'zetaris' }

export function mapNodeFor(node: TimelineNode): MapNodeId | null {
  if (node.kind === 'input') return node.title === 'Screenshot' ? 'shot' : 'event'
  if (node.kind === 'result') return 'output'
  if (node.kind === 'state') return 'zetaris'
  return NODE_FOR_AGENT[node.agent] ?? null
}

export function timelineKeyForMapNode(timeline: Timeline, visible: number, id: MapNodeId): string | null {
  const found = [...timeline.nodes.slice(0, visible)].reverse().find((n) => mapNodeFor(n) === id)
  return found?.key ?? null
}

const VERBS: Record<string, string> = {
  EXTRACT: 'Reading the screenshot', STORE: 'Saving evidence', CREATE: 'Forming an intention', REVISE: 'Revising the intention',
  MATCH: 'Checking relevance', NO_MATCH: 'No connection found', SURFACE: 'Worth surfacing', STAY_SILENT: 'Stay silent',
  REQUEST_REVISION: 'Sending it back', ASK: 'Needs clarification', VERIFY_CONTEXT: 'Needs verifying', VERIFIED: 'Context verified',
  UNVERIFIED: 'Could not verify', RETRY: 'Retrying once', FAILED: 'Failed safely', IGNORE: 'Nothing to track', ATTACH: 'Attaching evidence', RESOLVE: 'Marking done',
}
export const verb = (action: string) => VERBS[action] ?? action.replace('_', ' ').toLowerCase()

export interface NodeView { state: 'idle' | 'active' | 'done'; text: string; action?: string }
export interface MapView {
  nodes: Record<MapNodeId, NodeView>
  edges: Partial<Record<EdgeId, { state: 'used' | 'active'; dir: EdgeDir }>>
  provider: Record<'openai' | 'nvidia', string | null>
  routing: string | null
  outputLabel: string
  caption: { agent: string; action: string; reason: string } | null
  focusKey: string | null
}

const OUTPUT: Record<string, string> = { SURFACE: 'Surface', STAY_SILENT: 'Stay silent', ASK: 'Check-in', FAILED_SAFE: 'Stopped', STORED: 'Saved' }

/** Everything the diagram needs, computed from the trace so far. `focus` is the step being highlighted. */
export function buildMapView(timeline: Timeline, visibleCount: number, focusKey: string | null, animateFocus: boolean): MapView {
  const visible = timeline.nodes.slice(0, visibleCount)
  const idle = (): NodeView => ({ state: 'idle', text: 'Idle' })
  const nodes = Object.fromEntries((NODES.map((n) => [n.id, idle()]))) as Record<MapNodeId, NodeView>
  const edges: MapView['edges'] = {}
  const provider: MapView['provider'] = { openai: null, nvidia: null }
  let routing: string | null = null
  const focus = visible.find((n) => n.key === focusKey) ?? visible[visible.length - 1]

  visible.forEach((node, i) => {
    const prev = i > 0 && timeline.nodes[i - 1].runIndex === node.runIndex ? timeline.nodes[i - 1] : undefined
    for (const use of usesForStep(node, prev)) edges[use.id] = { state: 'used', dir: use.dir }
    const target = mapNodeFor(node)
    if (target) {
      const action = node.event?.action
      nodes[target] = { state: 'done', text: action ? verb(action) : target === 'output' ? '' : 'Received', action }
    }
    const receipt = node.event?.receipt
    if (receipt?.provider === 'openai' || receipt?.provider === 'nvidia') provider[receipt.provider] = modelLabel(receipt.routed_model)
  })

  let caption: MapView['caption'] = null
  if (focus) {
    const index = timeline.nodes.indexOf(focus)
    const prev = index > 0 && timeline.nodes[index - 1].runIndex === focus.runIndex ? timeline.nodes[index - 1] : undefined
    for (const use of usesForStep(focus, prev)) if (animateFocus) edges[use.id] = { state: 'active', dir: use.dir }
    const target = mapNodeFor(focus)
    if (target && animateFocus) nodes[target] = { ...nodes[target], state: 'active' }
    for (const use of usesForStep(focus, prev)) {
      if (!animateFocus) break
      if (use.id.startsWith('ns-') && use.id !== 'ns-openai' && use.id !== 'ns-nvidia') nodes.nightshift = { state: 'active', text: '' }
      if (use.id.startsWith('z-')) nodes.zetaris = { ...nodes.zetaris, state: 'active' }
    }
    const receipt = focus.event?.receipt
    if (receipt) routing = `${modelLabel(receipt.requested_model)} → ${modelLabel(receipt.routed_model)}`
    if (focus.event) caption = { agent: focus.event.agent, action: focus.event.action, reason: focus.event.reason }
    else if (focus.kind === 'result') caption = { agent: 'RESULT', action: focus.result!.run.final_action, reason: OUTPUT[focus.result!.run.final_action] ?? '' }
  }

  const lastResult = [...visible].reverse().find((n) => n.kind === 'result')
  const outputLabel = lastResult ? OUTPUT[lastResult.result!.run.final_action] ?? lastResult.result!.run.final_action : 'Output'
  return { nodes, edges, provider, routing, outputLabel, caption, focusKey: focus?.key ?? null }
}
