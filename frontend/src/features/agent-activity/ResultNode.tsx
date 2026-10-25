import { forwardRef } from 'react'
import { AgentIcon } from './agentMeta'
import type { TimelineNode } from './traceAdapter'

const RESULT_COPY: Record<string, { title: string; body: string }> = {
  SURFACE: { title: 'Recall surfaced this intention', body: 'Evidence and context both supported interrupting.' },
  STAY_SILENT: { title: 'Recall stayed silent', body: 'No interruption was warranted.' },
  ASK: { title: 'Recall needs clarification', body: 'A small answer would improve the interpretation.' },
  FAILED_SAFE: { title: 'Recall stopped safely', body: 'Something went wrong, so nothing was shown.' },
  STORED: { title: 'Recall saved this', body: 'Saving does not interrupt anyone.' },
}

const QUIET_ICON = new Set(['SURFACE', 'ASK'])

interface ResultProps { node: TimelineNode; visible: boolean; active: boolean; selected: boolean; onSelect: (key: string) => void }

const ResultNode = forwardRef<HTMLButtonElement, ResultProps>(function ResultNode({ node, visible, active, selected, onSelect }, ref) {
  const run = node.result!.run
  const copy = RESULT_COPY[run.final_action] ?? { title: run.final_action, body: '' }
  const payload = run.message_payload as { title?: string } | null
  const detail = run.final_action === 'ASK' ? run.question : payload?.title
  return (
    <button ref={ref} type="button" aria-pressed={selected} aria-hidden={!visible} tabIndex={visible ? 0 : -1} onClick={() => onSelect(node.key)}
      className={`aa-node aa-result aa-result-${run.final_action.toLowerCase().replace('_', '-')}${visible ? ' is-visible' : ''}${active ? ' is-active' : ''}${selected ? ' is-selected' : ''}`}>
      <span className="aa-node-icon"><AgentIcon agent="RESULT" quiet={!QUIET_ICON.has(run.final_action)} /></span>
      <span className="aa-node-body">
        <span className="aa-result-title">{copy.title}</span>
        {detail ? <span className="aa-node-headline">{detail}</span> : null}
        <span className="aa-node-reason">{copy.body}</span>
      </span>
    </button>
  )
})

export default ResultNode
