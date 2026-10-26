import { forwardRef } from 'react'
import { AGENTS, AgentIcon, EventSourceIcon } from './agentMeta'
import type { TimelineNode } from './traceAdapter'

interface Props {
  node: TimelineNode
  visible: boolean
  active: boolean
  selected: boolean
  onSelect: (key: string) => void
}

const EMPHASIS = new Set(['REQUEST_REVISION', 'VERIFY_CONTEXT', 'SURFACE', 'ASK'])
const MUTED = new Set(['RETRY', 'FAILED', 'UNVERIFIED'])

function pillClass(action: string) {
  if (EMPHASIS.has(action)) return 'aa-pill aa-pill-accent'
  if (MUTED.has(action)) return 'aa-pill aa-pill-muted'
  return 'aa-pill'
}

const EventNode = forwardRef<HTMLButtonElement, Props>(function EventNode({ node, visible, active, selected, onSelect }, ref) {
  const meta = AGENTS[node.agent]
  const isEvent = node.kind === 'event' && node.event
  const label = node.event?.agent === 'REPOSITORY' || node.kind === 'state' ? 'Repository' : node.agent === 'ZETARIS' ? 'Zetaris' : node.kind === 'input' ? node.title : meta.label
  const role = node.kind === 'input' ? 'Input' : meta.role
  const className = ['aa-node', `aa-node-${node.kind}`, `aa-agent-${node.agent.toLowerCase()}`, node.lane === 'branch' ? 'is-branch' : '',
    node.placeholder ? 'is-placeholder' : '', visible ? 'is-visible' : '', active ? 'is-active' : '', selected ? 'is-selected' : '',
    isEvent && EMPHASIS.has(node.event!.action) ? 'is-emphasis' : ''].filter(Boolean).join(' ')

  return (
    <button ref={ref} type="button" className={className} aria-pressed={selected} aria-hidden={!visible} tabIndex={visible ? 0 : -1}
      onClick={() => onSelect(node.key)} data-node-key={node.key}>
      <span className="aa-node-icon">{node.kind === 'input' && node.title === 'Calendar event' ? <EventSourceIcon /> : <AgentIcon agent={node.agent} />}</span>
      <span className="aa-node-body">
        <span className="aa-node-top">
          <span className="aa-node-label">
            {node.step ? <span className="aa-step">{String(node.step).padStart(2, '0')}</span> : null}
            {label}
            <span className="aa-node-role"> · {role}</span>
          </span>
          {isEvent ? <span className={pillClass(node.event!.action)}>{node.event!.action.replace('_', ' ')}</span> : null}
        </span>
        {node.headline ? <span className="aa-node-headline">{node.headline}</span> : null}
        {isEvent ? <span className="aa-node-reason">{node.event!.reason}</span> : null}
        {!isEvent && node.detail ? <span className="aa-node-reason">{node.detail}</span> : null}
        {node.placeholder ? <span className="aa-badge">Shared state</span> : null}
      </span>
    </button>
  )
})

export default EventNode
