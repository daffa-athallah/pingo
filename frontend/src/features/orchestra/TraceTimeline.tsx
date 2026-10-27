import { useState } from 'react'
import { agentKey, modelLabel, nextLabel, providerLabel } from '../agent-activity/agentMeta'
import type { RunRecord } from '../../services/runsApi'

function clock(timestamp: string | null) {
  const d = timestamp ? new Date(timestamp) : null
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
}
const HIDDEN = new Set(['STARTED', 'DECIDING'])
const ICON: Record<string, string> = { EVIDENCE: 'M12 5C6 5 2.5 12 2.5 12S6 19 12 19s9.5-7 9.5-7S18 5 12 5Zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-6a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z',
  ZETARIS: 'M12 3c4.4 0 8 1.3 8 3v12c0 1.7-3.6 3-8 3s-8-1.3-8-3V6c0-1.7 3.6-3 8-3Zm0 2c-3.9 0-6 1-6 1s2.1 1 6 1 6-1 6-1-2.1-1-6-1Zm-6 4.3V12c0 .4 2.1 1.4 6 1.4s6-1 6-1.4V9.3c-1.4.8-3.7 1.2-6 1.2s-4.6-.4-6-1.2Z',
  OPEN_LOOP: 'M6 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6V3Zm2 2v14h8V5H8Zm2 3h4v2h-4V8Zm0 4h4v2h-4v-2Z', CONTEXT: 'M9 4 3 6.5v13L9 17l6 3 6-2.5v-13L15 7 9 4Zm1 2.6 4 2v9.8l-4-2V6.6Z',
  CRITIC: 'M11 3h2v2.1l5.5 1.4-3 6.5a3.5 3.5 0 0 1-7 0l-3-6.5L11 5.1V3Zm-4.2 5.1 2.1 4.4H4.7l2.1-4.4Zm10.4 0 2.1 4.4h-4.2l2.1-4.4ZM8 19h8v2H8v-2Z',
  OTHER: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16Zm-1 4h2v5h-2V8Zm0 6h2v2h-2v-2Z' }
const kindOf = (agent: string) => { const k = agentKey(agent); return k === 'MEMORY' ? 'ZETARIS' : k === 'SOURCE' || k === 'RESULT' ? 'OTHER' : k }

/** What Pingo actually did in this run, in order. Only events that happened; reasons, results and receipts come from the recorded run. */
export default function TraceTimeline({ run, upTo }: { run: RunRecord; upTo?: number }) {
  const [open, setOpen] = useState<number | null>(null)
  const events = run.result.trace_events.slice(0, upTo ?? undefined)
  const revised = run.original_title && run.final_title && run.original_title !== run.final_title
  const evidence = run.outcome?.evidence
  const loop = run.outcome?.open_loop
  return <ol className="timeline">
    {events.filter((e) => !HIDDEN.has(e.action)).map((e, i) => {
      const kind = kindOf(e.agent)
      const label = e.agent === 'RUN' ? 'Pingo' : e.agent === 'UPLOAD' ? 'Screenshot' : e.agent === 'LOCATION' ? 'Map lookup' : e.agent === 'H-MEM' ? 'H-MEM' : e.agent === 'REPOSITORY' || e.agent === 'ZETARIS' ? 'Zetaris'
        : e.agent === 'EVIDENCE' ? 'Evidence Agent' : e.agent === 'OPEN_LOOP' ? 'Open Loop Agent' : e.agent === 'CONTEXT' ? 'Context Agent' : e.agent === 'CRITIC' ? 'Critic Agent' : e.agent
      const isOpen = open === i
      const bullets = e.agent === 'EVIDENCE' && e.action === 'EXTRACT' && evidence && !evidence.sensitive ? [
        evidence.domain ? `Topic: ${evidence.domain}` : null, ...(evidence.entities ?? []).slice(0, 4).map((x) => x.name)].filter(Boolean) as string[]
        : e.agent === 'OPEN_LOOP' && ['CREATE', 'ATTACH', 'REVISE'].includes(e.action) && loop?.loop ? [loop.loop.title] : []
      return <li key={e.seq ?? i} className={`tl-item tl-${kind.toLowerCase()}${e.action === 'REQUEST_REVISION' || e.action === 'REVISE' ? ' is-revision' : ''}`}>
        <span className="tl-icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICON[kind] ?? ICON.OTHER} /></svg></span>
        <div className="tl-body">
          <time>{clock(e.timestamp)}</time>
          <div className="tl-head"><strong>{label}</strong><b>{e.action.replaceAll('_', ' ')}</b></div>
          <p>{e.reason}</p>
          {bullets.length ? <div className="tl-result"><small>{e.agent === 'EVIDENCE' ? 'Identified' : 'Result'}</small><ul>{bullets.map((b) => <li key={b}>{b}</li>)}</ul></div> : null}
          {e.action === 'REVISE' && revised ? <div className="tl-before-after"><span>Before</span> “{run.original_title}”<br /><span>After</span> “{run.final_title}”</div> : null}
          {e.receipt && (e.receipt.routed_model || e.receipt.provider) ? <div className="tl-chips"><i>{modelLabel(e.receipt.routed_model) ?? e.receipt.routed_model ?? 'model'}</i><i>via Nightshift ✓</i>{e.receipt.provider ? <small>{providerLabel(e.receipt.provider)}</small> : null}</div> : null}
          <button className="tl-more" onClick={() => setOpen(isOpen ? null : i)} aria-expanded={isOpen}>{isOpen ? 'Hide details' : 'Details'}</button>
          {isOpen ? <dl className="tl-details">
            {e.next_step ? <><dt>Hands over to</dt><dd>{nextLabel(e.next_step)}</dd></> : null}
            {e.input_refs.length ? <><dt>Inputs</dt><dd>{e.input_refs.join(', ')}</dd></> : null}
            {e.output_ref ? <><dt>Output</dt><dd>{e.output_ref}</dd></> : null}
            {e.receipt ? <><dt>Receipt</dt><dd>requested {e.receipt.requested_model ?? '—'} · routed {e.receipt.routed_model ?? '—'} · {e.receipt.provider ?? '—'}</dd></> : null}
            <dt>Run</dt><dd>{e.run_id ?? run.run_id} · step {e.seq ?? i + 1}</dd>
          </dl> : null}
        </div>
      </li>
    })}
  </ol>
}
