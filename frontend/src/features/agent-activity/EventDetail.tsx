import type { TraceEvent } from './types'

// Structured inputs, retrievals, decisions and state changes recorded around the agents. Model reasoning is never recorded, so none is shown.

type Bag = Record<string, unknown>
const bag = (value: unknown): Bag => (value && typeof value === 'object' ? (value as Bag) : {})
const list = (value: unknown): Bag[] => (Array.isArray(value) ? value.map(bag) : [])
const strings = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [])
const text = (value: unknown) => (typeof value === 'string' && value ? value : null)
const num = (value: unknown) => (typeof value === 'number' ? value : null)

function Chips({ items }: { items: string[] }) {
  return <ul className="aa-chips">{items.map((item) => <li key={item}>{item}</li>)}</ul>
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="aa-detail"><h3>{title}</h3>{children}</section>
}

function Entity({ item }: { item: Bag }) {
  const extras = [text(item.type), text(item.brand), text(item.location_name) ?? text(item.city)].filter(Boolean).join(' · ')
  const attributes = Object.entries(bag(item.attributes)).map(([k, v]) => `${k}: ${String(v)}`)
  return <li><strong>{text(item.name)}</strong>{extras ? <small>{extras}</small> : null}{attributes.length ? <small>{attributes.join(' · ')}</small> : null}</li>
}

export default function EventDetail({ event }: { event: TraceEvent }) {
  const d = bag(event.detail)
  if (!event.detail) return null
  const key = `${event.agent}:${event.action}`

  if (key === 'EVIDENCE:EXTRACT') {
    if (d.sensitive) return <Section title="What it understood"><p className="aa-note">Flagged as sensitive. Nothing about its content is shown, and it is never sent to a reasoning model.</p></Section>
    return (
      <>
        <Section title="What it understood">
          <p className="aa-reason">{text(d.summary)}</p>
          <dl className="aa-kv"><dt>domain</dt><dd>{text(d.domain)}</dd><dt>confidence</dt><dd>{text(d.confidence)}</dd></dl>
        </Section>
        <Section title={`Entities (${list(d.entities).length})`}><ul className="aa-list">{list(d.entities).map((e, i) => <Entity key={i} item={e} />)}</ul></Section>
      </>
    )
  }

  if (event.action === 'STORE') {
    return (
      <Section title="Stored">
        <dl className="aa-kv">
          <dt>where</dt><dd>{text(d.backend)}</dd>
          <dt>new entities</dt><dd>{num(d.entities_new)}{strings(d.new_entities).length ? ` (${strings(d.new_entities).join(', ')})` : ''}</dd>
          <dt>matched existing</dt><dd>{num(d.entities_matched_existing)}{strings(d.matched_entities).length ? ` (${strings(d.matched_entities).join(', ')})` : ''}</dd>
          <dt>links</dt><dd>{num(d.links)}</dd>
        </dl>
      </Section>
    )
  }

  if (key === 'OPEN_LOOP:RETRIEVE') {
    const evidence = list(d.related_evidence)
    const loops = list(d.candidate_loops)
    const entities = list(d.related_entities)
    return (
      <>
        <p className="aa-note">Exactly what the Open Loop Agent was given to decide with, read from the repository.</p>
        <Section title={`Related Evidence (${evidence.length})`}>
          {evidence.length ? <ul className="aa-list">{evidence.map((e) => <li key={String(e.evidence_id)}>{text(e.summary)}<small>{String(e.evidence_id)}</small></li>)}</ul>
            : <p className="aa-note">None: no earlier screenshot shares an entity with this one.</p>}
        </Section>
        <Section title={`Related entities (${entities.length})`}>{entities.length ? <Chips items={entities.map((e) => String(e.name))} /> : <p className="aa-note">None.</p>}</Section>
        <Section title={`Candidate loops (${loops.length})`}>
          <ul className="aa-list">{loops.map((l) => <li key={String(l.loop_id)}>{text(l.title)}<small>{String(l.status)}{strings(l.entities).length ? ` · ${strings(l.entities).join(', ')}` : ''}</small></li>)}</ul>
        </Section>
      </>
    )
  }

  if (key === 'OPEN_LOOP:DECIDING') {
    return <Section title="Deciding with"><dl className="aa-kv"><dt>model</dt><dd>{text(d.model)}</dd><dt>related Evidence</dt><dd>{num(d.related_evidence)}</dd><dt>candidate loops</dt><dd>{num(d.candidate_loops)}</dd></dl></Section>
  }

  if (key === 'OPEN_LOOP:STATE') {
    const before = bag(d.before)
    const after = bag(d.after)
    return (
      <Section title="Loop state">
        <p className="aa-reason">{text(d.change)}</p>
        <div className="aa-ba">
          <div><span>before</span>{d.before ? <><strong>{num(before.screenshots)}</strong><small>{text(before.title)}</small></> : <strong>·</strong>}</div>
          <i aria-hidden="true">→</i>
          <div><span>after</span><strong>{num(after.screenshots)}</strong><small>{text(after.title)}</small></div>
        </div>
        <p className="aa-note">Supporting screenshots, as counted by the app.</p>
      </Section>
    )
  }

  if (event.agent === 'OPEN_LOOP' && num(d.confidence) !== null) {
    const confidence = num(d.confidence) ?? 0
    return (
      <>
        <Section title="Decision">
          <dl className="aa-kv">
            <dt>action</dt><dd>{text(d.decision)}</dd>
            {text(d.target_loop_id) ? <><dt>target loop</dt><dd>{text(d.target_loop_id)}</dd></> : null}
            {text(d.proposed_title) ? <><dt>title</dt><dd>{text(d.proposed_title)}</dd></> : null}
            <dt>domain</dt><dd>{text(d.domain)}</dd>
          </dl>
          <p className="aa-note">Confidence {Math.round(confidence * 100)}%</p>
          <div className="aa-bar" role="img" aria-label={`Confidence ${Math.round(confidence * 100)} percent`}><i style={{ width: `${Math.round(confidence * 100)}%` }} /></div>
        </Section>
        {strings(d.supporting_evidence_ids).length ? <Section title="Supporting Evidence"><Chips items={strings(d.supporting_evidence_ids)} /></Section> : null}
        {strings(d.supporting_entity_ids).length ? <Section title="Supporting entities"><Chips items={strings(d.supporting_entity_ids)} /></Section> : null}
        {text(d.material_uncertainty) ? <Section title="Material uncertainty"><p className="aa-reason">{text(d.material_uncertainty)}</p></Section> : null}
      </>
    )
  }

  if (event.agent === 'UPLOAD') {
    return <Section title="Upload"><dl className="aa-kv">{Object.entries(d).map(([k, v]) => <><dt key={`k${k}`}>{k.replace('_', ' ')}</dt><dd key={`v${k}`}>{String(v)}</dd></>)}</dl></Section>
  }
  return null
}
