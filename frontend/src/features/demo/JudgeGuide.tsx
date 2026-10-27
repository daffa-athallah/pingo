import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getCachedHistory, getHealth } from '../../services/runsApi'
import type { CachedHistory } from '../../services/runsApi'
import TryPanel from './TryPanel'
import ZetarisPanel from './ZetarisPanel'
import './judge-guide.css'

const KEY = 'recall.history-guide.v1'
const STEPS = ['Saved for later', 'The evidence is still here', 'An interest, not a plan', 'A reason to remember', 'Knowing when to stay quiet']

function subject(title: string) { return title.replace(/^Interested in\s+/i, '').replace(/\s*\([^)]*\)\s*$/, '') }
function date(value?: string) {
  return value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : 'an earlier run'
}

/** Guidance around the actual product routes, backed only by saved run metadata. */
export default function JudgeGuide() {
  const [history, setHistory] = useState<CachedHistory | null>(null)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(() => { try { return sessionStorage.getItem(KEY) !== 'closed' } catch { return true } })
  const [step, setStep] = useState(0)
  const [tab, setTab] = useState<'tour' | 'try' | 'data'>('tour')
  const [tried, setTried] = useState(false)  // the Try it tab pulses until it has been opened once
  const location = useLocation()
  const navigate = useNavigate()
  const recall = history?.recall_views[0]
  const quiet = history?.records.find(run => run.result.final_action === 'STAY_SILENT' && (run.context_event || run.context_events?.length))
  const quietContext = quiet?.context_event ?? quiet?.context_events?.[0]

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(health => {
      if (health.mode === 'sample') return getCachedHistory(controller.signal).then(setHistory)
    }).catch(() => { if (!controller.signal.aborted) setError('Cached history could not be loaded.') })
    return () => controller.abort()
  }, [])

  useEffect(() => {  // the Try it panel asks for the guide while a walkthrough moves between screens
    const show = () => { setOpen(true); setTab('try'); setTried(true) }
    window.addEventListener('recall:guide-open', show)
    return () => window.removeEventListener('recall:guide-open', show)
  }, [])

  useEffect(() => {
    if (new URLSearchParams(location.search).get('guide') === '1') { setOpen(true); setStep(0) }
  }, [location.search])

  const route = recall ? step === 0 || step === 4 ? '/' : step < 3 ? `/entity/${recall.loop_id}` : `/recalls/${recall.notification_id}` : '/'
  const onRoute = location.pathname === route

  useEffect(() => {
    if (!open || !recall || !onRoute) return
    let target: HTMLElement | null = null
    const find = () => {
      if (target) return
      target = step === 0
        ? [...document.querySelectorAll<HTMLAnchorElement>('a[href]')].find(a => a.getAttribute('href') === `/entity/${recall.loop_id}`) ?? null
        : document.querySelector<HTMLElement>(step === 1 ? '[data-guide-target="screenshots"]' : step === 2 ? '[data-guide-target="intention"]' : '.pingo-recall-detail section')
      if (target) { target.classList.add('guide-focus'); target.scrollIntoView({ block: 'center', behavior: 'smooth' }) }
    }
    find()
    const observer = new MutationObserver(find)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => { observer.disconnect(); target?.classList.remove('guide-focus') }
  }, [open, step, recall, onRoute])

  if (!history) return error ? <aside className="guide-status" role="status">{error}</aside> : null
  const close = () => { setOpen(false); try { sessionStorage.setItem(KEY, 'closed') } catch { /* optional preference */ } }
  const move = (next: number) => {
    setStep(next)
    if (!recall) return
    navigate(next === 0 || next === 4 ? '/' : next < 3 ? `/entity/${recall.loop_id}` : `/recalls/${recall.notification_id}`)
  }
  const title = recall ? subject(recall.title) : 'Your saved history'
  const copy = !recall ? 'Browse the saved intentions and their original screenshots. No stored reminder decision matches this snapshot, so this guide will not invent one.'
    : step === 0 ? `You saved ${title} for later. It is one of the interests already in this history. Open it to see what Pingo actually knows.`
      : step === 1 ? `These ${recall.evidence_ids.length} screenshots are the source. Pingo keeps them attached to the interest, so you can go back to what you saved.`
        : step === 2 ? 'Saving a place does not mean you booked it or decided to go. This is a tentative interest, grounded in the screenshots above.'
          : step === 3 ? `In the saved run, “${recall.context?.title ?? 'a context event'}”${recall.context?.location_name ? ` in ${recall.context.location_name}` : ''} made that interest relevant. The saved reminder keeps the reason and the supporting screenshots together.`
            : quiet ? `A separate saved event, “${quietContext?.title ?? 'an unrelated event'}”, ended in ${quiet.result.final_action?.replaceAll('_', ' ')}. No reminder was approved. The system does not need to interrupt for every saved interest.`
              : 'This history has no saved restraint decision to show. Pingo’s trace is available below; no additional outcome is invented.'

  return <>
    <div className="guide-status" role="status"><span className="guide-status-dot" />Recorded examples <span>· No live model runs</span><button className={`guide-toggle${open ? '' : ' is-attention'}`} onClick={() => setOpen(value => !value)}>{open ? 'Hide guide' : 'Show guide'}</button></div>
    {location.pathname === '/check-in' && <div className="guide-hint" role="note">
      <strong>Recorded example.</strong> A Check-in only appears when the Critic is unsure whether two saves are the same thing.
      <button onClick={() => { setOpen(true); setTab('try'); window.dispatchEvent(new CustomEvent('recall:play', { detail: 'duplicates' })) }}>See how one is made →</button>
    </div>}
    <aside className="history-guide" hidden={!open} aria-label="Guide to Pingo">
      <div className="history-guide-meta"><span>Explore Pingo</span><span>{step + 1} / {STEPS.length}</span><button aria-label="Close guide" onClick={close}>×</button></div>
      <div className="history-guide-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'tour'} onClick={() => setTab('tour')}>Tour</button>
        <button role="tab" className={tried ? '' : 'is-attention'} aria-selected={tab === 'try'} onClick={() => { setTab('try'); setTried(true) }}>Try it</button>
        <button role="tab" aria-selected={tab === 'data'} onClick={() => setTab('data')}>Zetaris</button>
      </div>
      <div hidden={tab !== 'try'}><TryPanel /></div>
      {tab === 'data' && <ZetarisPanel />}
      {tab === 'tour' && <>
      <h2>{STEPS[step]}</h2>
      <p>{copy}</p>
      {step >= 3 && recall && <p className="history-guide-source">Saved {date(recall.captured_at)} · {recall.synthetic_inputs ? 'Simulated calendar input' : 'Saved context'} · feedback changes this local copy only. This view does not claim a notification was delivered.</p>}
      {!onRoute && recall && <button className="history-guide-route" onClick={() => navigate(route)}>Return to this part of the story</button>}
      <div className="history-guide-controls">
        {step > 0 ? <button onClick={() => move(step - 1)}>Back</button> : <button onClick={close}>Explore on my own</button>}
        {step < STEPS.length - 1 && recall ? <button className="history-guide-next" onClick={() => move(step + 1)}>{step === 0 ? 'Open saved interest' : step === 2 ? 'See why it mattered' : 'Continue'}<span aria-hidden="true"> →</span></button>
          : <button className="history-guide-next" onClick={close}>Keep exploring →</button>}
      </div>
      {step === STEPS.length - 1 && recall && <Link className="history-guide-proof" to={`/agent-activity?demo=${quiet?.run_id ?? recall.run_id}`}>Inspect the saved agent decisions ↗</Link>}
      </>}
    </aside>
  </>
}
