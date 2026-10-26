import { AGENTS, AgentIcon, nextLabel, receiptSummary } from './agentMeta'
import EventDetail from './EventDetail'
import { refParts } from './traceAdapter'
import type { TimelineNode } from './traceAdapter'

function time(timestamp: string | null) {
  if (!timestamp) return null
  const d = new Date(timestamp)
  return Number.isNaN(d.getTime()) ? timestamp : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function Refs({ refs }: { refs: string[] }) {
  return (
    <ul className="aa-chips">
      {refs.map((ref) => {
        const { kind, id } = refParts(ref)
        return <li key={ref}><span>{kind}</span>{id}</li>
      })}
    </ul>
  )
}

/** `note` says when a trace is not a live run (scripted sample, hand-written illustration, recorded run). Null for a live run. */
export default function EventInspector({ node, note }: { node: TimelineNode | null; note: string | null }) {
  if (!node) {
    return (
      <aside className="aa-inspector" aria-live="polite">
        <p className="aa-inspector-empty">Select a step to see why it happened, what it used and which model ran it.</p>
      </aside>
    )
  }

  const meta = AGENTS[node.agent]
  const event = node.event
  const receipt = receiptSummary(event?.receipt ?? null)
  const placeholder = Boolean(node.placeholder)
  const title = node.kind === 'result' ? 'Final decision' : node.kind === 'input' || node.kind === 'state' ? node.title : meta.label

  return (
    <aside className="aa-inspector" aria-live="polite">
      <header className={`aa-inspector-head${node.kind === 'result' && !['SURFACE', 'ASK'].includes(node.result!.run.final_action) ? ' is-quiet' : ''}`}>
        <span className="aa-node-icon"><AgentIcon agent={node.agent} quiet={node.kind === 'result' && !(['SURFACE', 'ASK'].includes(node.result!.run.final_action))} /></span>
        <div>
          <p className="aa-inspector-eyebrow">{event?.agent === 'REPOSITORY' ? 'Demo workspace · Shared state (in-memory, not Zetaris)' : node.agent === 'ZETARIS' ? 'Zetaris · Shared state' : `${title} · ${meta.role}`}</p>
          <h2>{event ? event.action.replace('_', ' ') : node.kind === 'result' ? node.result!.run.final_action.replace('_', ' ') : node.title}</h2>
        </div>
      </header>

      {meta.question && node.kind === 'event' ? <p className="aa-question">“{meta.question}”</p> : null}

      {event ? (
        <section>
          <h3>Reason</h3>
          <p className="aa-reason">{event.reason}</p>
        </section>
      ) : null}

      {node.kind === 'result' ? (
        <section>
          <h3>Outcome</h3>
          <p className="aa-reason">
            {node.result!.run.final_action === 'ASK' ? node.result!.run.question
              : (node.result!.run.message_payload as { reason?: string } | null)?.reason ?? 'The run ended here with nothing shown to the user.'}
          </p>
          {node.result!.run.error ? <p className="aa-note">{node.result!.run.error}</p> : null}
        </section>
      ) : null}

      {node.kind !== 'event' && node.kind !== 'result' && node.detail ? (
        <section><h3>{node.kind === 'state' ? 'Read from shared state' : 'Details'}</h3><p className="aa-reason">{node.detail}</p></section>
      ) : null}

      {event ? <EventDetail event={event} /> : null}
      {event && event.input_refs.length ? <section><h3>Inputs</h3><Refs refs={event.input_refs} /></section> : null}
      {event?.output_ref ? <section><h3>Output</h3><Refs refs={[event.output_ref]} /></section> : null}

      {receipt ? (
        <section className="aa-routing">
          <h3>Routing</h3>
          <p className="aa-routing-title">Meterless Nightshift</p>
          <div className="aa-route-pair">
            <p><span>requested</span>{receipt.requested}</p>
            <i aria-hidden="true">→</i>
            <p><span>routed</span>{receipt.routed}</p>
          </div>
          <p className="aa-routing-line"><span>provider</span> {receipt.provider}</p>
          <details>
            <summary>Technical detail</summary>
            <code>{receipt.rawRequested}</code>
            <code>{receipt.rawRouted}</code>
          </details>
        </section>
      ) : event && !placeholder && event.agent !== 'VERIFIER' && !['REPOSITORY', 'ZETARIS', 'UPLOAD'].includes(event.agent) && event.action !== 'STATE' && event.action !== 'RETRIEVE' && event.action !== 'DECIDING' ? (
        <section className="aa-routing"><h3>Routing</h3><p className="aa-note">No routing receipt was recorded for this step.</p></section>
      ) : null}

      {placeholder ? (
        <section className="aa-routing">
          <h3>Zetaris</h3>
          <p className="aa-note">Shared repository state. This diagram node is a visual aid, not a recorded Zetaris query. The workspace label identifies the storage used.</p>
        </section>
      ) : null}

      {event?.agent === 'VERIFIER' ? (
        <section className="aa-routing"><h3>Verification</h3><p className="aa-note">A boundary check against a real source. No model is involved.</p></section>
      ) : null}

      {event && nextLabel(event.next_step) ? (
        <section><h3>Next</h3><p className="aa-next">→ {nextLabel(event.next_step)}</p></section>
      ) : null}

      <footer className="aa-inspector-foot">
        {event?.timestamp ? <span>{time(event.timestamp)}</span> : null}
        {event?.run_id ? <span>{event.run_id}</span> : null}
        {note ? <span>{note}</span> : null}
      </footer>
    </aside>
  )
}
