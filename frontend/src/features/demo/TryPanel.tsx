import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { API_BASE_URL } from '../../services/api'
import { getHealth, getSampleCases, replaySampleCase, resetSample } from '../../services/runsApi'
import type { RunRecord, SampleCase } from '../../services/runsApi'

const AGENT: Record<string, string> = { UPLOAD: 'Upload', EVIDENCE: 'Evidence Agent', REPOSITORY: 'Saved history', 'H-MEM': 'Memory (H-MEM)', OPEN_LOOP: 'Open Loop Agent', CONTEXT: 'Context Agent', CRITIC: 'Critic', ZETARIS: 'Storage', RUN: 'Result' }
const TEXT: Record<string, { title: string; hint: string }> = {
  attach: { title: "Elmo's burger, another screenshot", hint: 'Does Pingo see it is the same interest?' },
  create: { title: 'A venue you have never saved', hint: 'Does Pingo start a new intention?' },
  sensitive: { title: 'A screenshot with a password', hint: 'Does Pingo look at it?' },
  surface: { title: 'Dinner in Fitzroy North tonight', hint: 'A calendar event near a saved place. Does Pingo speak up?' },
  restraint: { title: 'Pick up dry cleaning', hint: 'An unrelated errand. Does Pingo stay quiet?' },
  revision: { title: 'An intention that is too specific', hint: 'Can the Critic send it back before Pingo speaks?' },
  duplicates: { title: 'Look-alike saves', hint: 'The Critic merges, separates, or asks you.' },
}
const GROUPS: { heading: string; cases: string[] }[] = [
  { heading: 'Save a screenshot', cases: ['attach', 'create', 'sensitive'] },
  { heading: 'Daily Check-in', cases: ['duplicates'] },
  { heading: 'Simulate where you are', cases: ['surface', 'restraint'] },
  { heading: 'Self-correction', cases: ['revision'] },
]
const STEP_MS = 650

function conclusion(run: RunRecord) {
  const out = run.outcome
  if (out) {
    if (out.evidence?.sensitive) return 'Saved, not analysed. It was flagged as sensitive, so no model reasoned over it and nothing about it is shown.'
    const loop = out.open_loop
    return `${out.evidence?.summary ?? 'Saved.'} → ${loop.decision ?? 'stored'}${loop.loop ? `: “${loop.loop.title}”` : ''}${loop.change ? ` (${loop.change.change})` : ''}`
  }
  if (run.check_ins?.length) return `Check-in: ${run.check_ins[0].question}`
  const events = run.result.trace_events
  const critic = [...events].reverse().find(event => event.agent === 'CRITIC')
  return `${run.result.final_action?.replaceAll('_', ' ') ?? 'Done'}${critic ? ` — ${critic.reason}` : ''}`
}

function Change({ run }: { run: RunRecord }) {
  const open = run.outcome?.open_loop
  const change = open?.change
  const loop = open?.loop
  if (!loop || !change) return null
  const before = change.before?.screenshots
  const after = change.after.screenshots
  const image = run.outcome?.evidence?.image_url
  const created = before == null
  return <div className="try-change" aria-label="What changed">
    <p className="try-change-title">{created ? 'New intention' : 'Updated intention'} · {open.decision}</p>
    <p className="try-change-loop">{loop.title}</p>
    <p className="try-change-count">
      {created ? <strong>{after} screenshot</strong> : <><span>{before}</span><span className="try-arrow" aria-label="became">→</span><strong>{after} screenshots</strong></>}
      {image && <img src={`${API_BASE_URL.replace(/\/$/, '')}${image}`} alt="The new screenshot" />}
    </p>
    <p className="try-change-note">Shown on this replay's own copy of the saved history; the intentions on Home are not changed.</p>
  </div>
}

interface TourStep { title: string; text: string; by?: string[]; route: string; find?: () => HTMLElement | null; mark?: boolean }

/** What changed in the product screens after a replay, as a short guided walk through those screens. */
function said(run: RunRecord, agent: string, action: string) {
  const event = run.result.trace_events.find(item => item.agent === agent && item.action === action)
  return event ? `${AGENT[agent] ?? agent} · ${action.replaceAll('_', ' ')}: ${event.reason}` : null
}

const short = (text: string) => (text.length > 120 ? `${text.slice(0, 117)}…` : text)

function reviewFlow(run: RunRecord) {
  return run.result.trace_events.flatMap(event => {
    if (event.agent === 'REPOSITORY' && event.action === 'LOAD') return [`Saved history → Critic: ${short(event.reason)}`]
    if (event.agent !== 'CRITIC') return []
    if (event.action === 'MERGE') return [`Critic → Saved history (merge): ${short(event.reason)}`]
    if (event.action === 'ASK') return [`Critic → Check-in → you: ${short(event.reason)}`]
    return [`Critic → no change (${event.action.replaceAll('_', ' ').toLowerCase()}): ${short(event.reason)}`]
  })
}

const AGENT_NAME: Record<string, string> = { CONTEXT: 'Context Agent', CRITIC: 'Critic', OPEN_LOOP: 'Open Loop Agent', REPOSITORY: 'Saved history', OUTPUT: 'you', STOP: 'nobody' }
const talk = (run: RunRecord) => run.result.trace_events.filter(e => ['CONTEXT', 'CRITIC', 'OPEN_LOOP'].includes(e.agent))
  .map(e => `${AGENT_NAME[e.agent]} → ${AGENT_NAME[e.next_step ?? ''] ?? e.next_step ?? 'end'} (${e.action.replaceAll('_', ' ').toLowerCase()}): ${short(e.reason)}`)

function contextTour(run: RunRecord, kase: string): TourStep[] {
  const event = run.context_event ?? run.context_events?.[0]
  const where = event ? `“${event.title}”${event.location_name ? ` in ${event.location_name}` : ''}` : 'a calendar event'
  if (kase === 'restraint') {
    return [{ title: 'Nothing appears, on purpose', route: '/', by: talk(run),
      text: `${where} came in. No saved intention clearly applies, so Pingo stays silent: no banner, no notification. Restraint is a decision the agents make and record.` }]
  }
  const id = run.notification_id
  const steps: TourStep[] = [{ title: kase === 'revision' ? 'The Critic sends it back, then agrees' : 'The agents agree to speak up', route: '/', by: talk(run),
    text: kase === 'revision'
      ? `${where} matched a saved intention, but its title promised a booking the screenshots never showed. The Critic requested a revision, the Open Loop Agent rewrote it as an interest, and only then did the Critic approve.`
      : `${where} matched a saved interest. The Critic checked the evidence and approved a reminder.` }]
  if (id) {
    steps.push({ title: 'The ping reaches you', route: '/', text: 'It appears in the app as a banner, with the reason in one line. In a real session it can also arrive as a phone notification.',
      find: () => document.querySelector<HTMLElement>(`a[href="/recalls/${id}"]`) ?? document.querySelector<HTMLElement>('.pingo-notice') })
    steps.push({ title: 'Why now, with the evidence', route: `/recalls/${id}`, text: 'Open the ping to see the reason it appeared and the screenshots behind it. Nothing is claimed without evidence.',
      find: () => document.querySelector<HTMLElement>('.pingo-why-now') })
  }
  return steps
}

function tourFor(run: RunRecord): TourStep[] {
  const out = run.outcome
  const open = out?.open_loop
  const loop = open?.loop
  const kase = run.run_id.replace('run_sample_', '')
  if (kase === 'duplicates') {
    const c = (run as RunRecord & { consolidation?: { merged: unknown[]; asked: unknown[]; kept_separate: number } }).consolidation
    return [
      { title: 'The Critic reviews look-alike saves', route: '/', by: reviewFlow(run),
        text: `Six synthetic look-alike intentions were added to Home for this example. The Critic judged each close pair: ${c?.merged.length ?? 0} merged, ${c?.kept_separate ?? 0} kept separate, ${c?.asked.length ?? 0} it was not sure about.` },
      { title: 'Where it is unsure, it asks you', route: '/check-in', find: () => document.querySelector<HTMLElement>('.checkin-card'),
        by: ['Critic → Check-in: the question above, with its reason', 'Check-in → you: one question a day, never a guess'],
        text: 'The Critic does not decide on its own when two saves might be one thing. The question is waiting here, in the real daily Check-in.' },
      { title: 'Your answer is what merges', route: '/check-in', find: () => document.querySelector<HTMLElement>('.checkin-card'),
        by: ['you → Check-in: “Yes, same thing”', 'Check-in → Saved history: the two intentions become one'],
        text: 'Try it: answer the question. Only your “same thing” folds the two intentions together; “keep both” or “related” leaves them as they are.' },
    ]
  }
  if (kase === 'surface' || kase === 'revision' || kase === 'restraint') return contextTour(run, kase)
  if (!out || !out.evidence) return []
  if (out.evidence.sensitive) return [{ title: 'Nothing appears', route: '/', text: 'Home has no new intention. The screenshot was saved as Evidence and flagged sensitive, so no reasoning model read it, memory did not keep it, and its image was never shown.' }]
  if (!loop) return []
  const change = open?.change
  const before = change?.before?.screenshots
  const target = () => [...document.querySelectorAll<HTMLAnchorElement>('a[href]')].find(a => a.getAttribute('href') === `/entity/${loop.loop_id}`) ?? null
  const created = before == null
  return [
    { title: created ? 'A new intention on Home' : 'The same intention, one more screenshot', route: '/', find: target,
      by: [said(run, 'OPEN_LOOP', 'ATTACH') ?? said(run, 'OPEN_LOOP', 'CREATE'), said(run, 'H-MEM', 'QUERY')].filter((x): x is string => !!x),
      text: created ? `Pingo started “${loop.title}” from this screenshot, because nothing saved matched it.`
        : `Pingo recognised this as the same interest, not a new one: “${loop.title}” now has ${change?.after.screenshots} screenshots, up from ${before}.` },
    { title: created ? 'Open it: the source is there' : 'Here is the new screenshot', route: `/entity/${loop.loop_id}`, mark: true,
      find: () => document.querySelector<HTMLElement>(`img[src*="/evidence/${out.evidence?.evidence_id}/image"]`)?.parentElement ?? null,
      by: [said(run, 'EVIDENCE', 'EXTRACT'), said(run, 'REPOSITORY', 'STORE')].filter((x): x is string => !!x),
      text: created ? 'The intention keeps the screenshot it came from.' : `The newest screenshot sits with the ${before} you already had.` },
  ]
}

/** Replays a bundled example through the real agents. Replies come from earlier captures, so no model runs, and the steps are revealed one at a time. */
export default function TryPanel() {
  const [cases, setCases] = useState<SampleCase[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [shown, setShown] = useState(0)
  const [error, setError] = useState('')
  const timer = useRef<number | undefined>(undefined)
  const [step, setStep] = useState(-1)
  const [live, setLive] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(health => setLive(!!health.live_models)).catch(() => undefined)
    getSampleCases(controller.signal).then(setCases).catch(() => { if (!controller.signal.aborted) setError('The examples could not be loaded.') })
    return () => { controller.abort(); window.clearInterval(timer.current) }
  }, [])

  const play = async (name: string) => {
    window.clearInterval(timer.current)
    setError(''); setRun(null); setShown(0); setStep(-1); setActive(name)
    try {
      const record = await replaySampleCase(name)
      window.dispatchEvent(new Event('recall:data-changed'))
      setRun(record)
      let count = 0
      timer.current = window.setInterval(() => {
        count += 1; setShown(count)
        if (count >= record.result.trace_events.length) { window.clearInterval(timer.current); setActive(null); window.dispatchEvent(new Event('pingo-notifications-changed')) }
      }, STEP_MS)
    } catch (e) { setActive(null); setError(e instanceof Error ? e.message : 'Replay failed.') }
  }

  const events = run?.result.trace_events ?? []
  const done = run != null && shown >= events.length
  const tour = run && done ? tourFor(run) : []
  const current = step >= 0 ? tour[step] : undefined
  const go = (next: number) => { setStep(next); window.dispatchEvent(new Event('recall:guide-open')); if (tour[next]) navigate(tour[next].route) }
  const clear = async () => {
    window.clearInterval(timer.current)
    try { await resetSample() } catch { /* the page still works without it */ }
    window.dispatchEvent(new Event('recall:data-changed'))
    window.dispatchEvent(new Event('pingo-notifications-changed'))
    setRun(null); setStep(-1); setShown(0); setActive(null)
    navigate('/')
  }

  useEffect(() => {
    document.body.classList.toggle('guide-touring', !!current)
    return () => document.body.classList.remove('guide-touring')
  }, [current])

  const playRef = useRef(play)
  playRef.current = play
  useEffect(() => {  // other screens (the empty Check-in page) can start a recorded example
    const start = (event: Event) => void playRef.current(String((event as CustomEvent).detail))
    window.addEventListener('recall:play', start)
    return () => window.removeEventListener('recall:play', start)
  }, [])

  const runRef = useRef<HTMLDivElement>(null)
  const endRef = useRef<HTMLDivElement>(null)
  // Follow the run: each new step scrolls into view, and when it finishes the result and the "Show me what changed" button are in view.
  useEffect(() => { if (run && !current) endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [run, shown, current])

  useEffect(() => {
    if (!current || location.pathname !== current.route) return
    let target: HTMLElement | null = null
    const find = () => {
      if (target || !current.find) return
      target = current.find()
      if (target) { target.classList.add('guide-focus'); if (current.mark) target.classList.add('guide-new'); target.scrollIntoView({ block: 'start', behavior: 'smooth' }) }
    }
    find()
    const observer = new MutationObserver(find)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => { observer.disconnect(); target?.classList.remove('guide-focus', 'guide-new') }
  }, [current, location.pathname])
  return <div className="try-panel">
    {!current && live && <p className="try-note">Live models are configured. <Link to="/sync">Try your own screenshot →</Link> It runs the same agents on the sample workspace, with real model calls.</p>}
    {!current && GROUPS.map(group => <section key={group.heading}>
      <h3>{group.heading}</h3>
      <div className="try-options">
        {cases.filter(item => group.cases.includes(item.case)).map(item => <button key={item.case} disabled={active !== null} className={run?.run_id.endsWith(item.case) ? 'is-current' : ''} onClick={() => void play(item.case)}>
          {item.image_url ? <img src={`${API_BASE_URL.replace(/\/$/, '')}${item.image_url}`} alt="" /> : item.sensitive ? <span className="try-lock" aria-hidden="true">🔒</span> : null}
          <span><strong>{TEXT[item.case]?.title ?? item.label}</strong><small>{TEXT[item.case]?.hint}</small></span>
        </button>)}
      </div>
    </section>)}
    {!current && <button className="try-reset" onClick={() => void clear()}>Reset example data</button>}
    {error && <p className="try-error" role="alert">{error}</p>}
    {run && <div className="try-run" ref={runRef} aria-live="polite">
      {!current && <p className="try-note">Recorded run, replayed. The agents run for real; model answers come from an earlier capture. Inputs are synthetic.</p>}
      {!current && <ol>{events.slice(0, shown).map((event, index) => <li key={index} className={index === shown - 1 && !done ? 'is-latest' : ''}>
        <span className="try-agent">{AGENT[event.agent] ?? event.agent}</span> <span className="try-action">{event.action.replaceAll('_', ' ')}</span>
        <span className="try-reason">{event.reason}</span>
      </li>)}</ol>}
      {!done && <p className="try-thinking"><span className="guide-status-dot" /> Agents working…</p>}
      {done && !current && <Change run={run} />}
      {done && !current && <><p className="try-result">{conclusion(run)}</p>
        {tour.length > 0 && <button className="history-guide-next try-tour-start" onClick={() => go(0)}>Show me what changed <span aria-hidden="true">→</span></button>}
        <Link className="history-guide-proof" to={`/agent-activity?demo=${run.run_id}`}>Inspect every step ↗</Link></>}
      <div ref={endRef} aria-hidden="true" />
      {current && <div className="try-tour">
        <p className="try-tour-count">What changed · {step + 1} / {tour.length}</p>
        <h4>{current.title}</h4>
        <p>{current.text}</p>
        {current.by && current.by.length > 0 && <ul className="try-by">{current.by.map(line => <li key={line}>{line}</li>)}</ul>}
        <div className="history-guide-controls">
          <button onClick={() => step === 0 ? setStep(-1) : go(step - 1)}>{step === 0 ? 'Back to the trace' : 'Back'}</button>
          {step < tour.length - 1 ? <button className="history-guide-next" onClick={() => go(step + 1)}>Next →</button>
            : <button className="history-guide-next" onClick={() => setStep(-1)}>Done</button>}
        </div>
      </div>}
    </div>}
  </div>
}
