import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getRunRecords } from '../../services/runsApi'
import type { RunRecord } from '../../services/runsApi'
import LocationPrompts from '../demo/LocationPrompts'
import OrchestraStage from './OrchestraStage'
import TraceTimeline from './TraceTimeline'
import { caption, frameAt } from './orchestraModel'
import { useSync } from './syncStore'
import { useNearby } from '../nearby/nearbyStore'
import type { Frame } from './orchestraModel'
import './orchestra.css'

const STEP_MS = 850
const reduceMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
const clock = (t: string | null) => { const d = t ? new Date(t) : null; return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '' }

/** The reasoning orchestra for one run, and the plain trace of what actually happened. Live while a run executes; otherwise the latest run, replayed. */
export default function AgentOrchestra() {
  const [runs, setRuns] = useState<RunRecord[]>([])
  const [params] = useSearchParams()
  const [picked, setPicked] = useState<string | null>(params.get('run') ?? params.get('demo'))
  const [tab, setTab] = useState<'orchestra' | 'trace'>('orchestra')
  const [shown, setShown] = useState(0)
  const [replaying, setReplaying] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const sync = useSync()
  const nearby = useNearby()

  const anyRunning = sync.busy || runs.some((r) => r.status === 'running')
  useEffect(() => {
    const controller = new AbortController()
    const load = () => getRunRecords(controller.signal).then((v) => setRuns(v)).catch(() => undefined)
    void load()
    const id = window.setInterval(load, anyRunning ? 1000 : 20000)
    return () => { controller.abort(); window.clearInterval(id) }
  }, [anyRunning])

  // The latest location check of this session joins the server's runs (it is a real run, just not listed by the server).
  const allRuns = useMemo(() => (nearby.last && !runs.some((r) => r.run_id === nearby.last?.run_id) ? [nearby.last, ...runs] : runs)
    .slice().sort((a, b) => (b.started_at ?? '').localeCompare(a.started_at ?? '')), [runs, nearby.last])
  const run = useMemo(() => {
    const byId = (id: string | null) => (id ? allRuns.find((r) => r.run_id === id) : undefined)
    return byId(picked) ?? byId(sync.runId) ?? allRuns.find((r) => r.status === 'running') ?? allRuns[0]
  }, [allRuns, picked, sync.runId])
  const working = nearby.checking && !picked ? nearby.checking : null
  const total = run?.result.trace_events.length ?? 0

  const play = (steps: number) => {
    window.clearInterval(timer.current)
    setShown(0); setReplaying(true)
    let n = 0
    timer.current = window.setInterval(() => {
      n += 1; setShown(n)
      if (n >= steps) { window.clearInterval(timer.current); setReplaying(false) }
    }, STEP_MS)
  }
  // A run that is executing is followed as its events arrive. A finished one is replayed once, then rests on its last step.
  const runId = run?.run_id
  const running = run?.status === 'running'
  const watched = useRef<{ id?: string; running: boolean }>({ running: false })  // a run seen executing is already "shown"; do not replay it from the start when it ends
  useEffect(() => {
    window.clearInterval(timer.current)
    const justFinished = watched.current.id === runId && watched.current.running && !running
    watched.current = { id: runId, running: Boolean(running) }
    if (!runId) { setShown(0); return undefined }
    if (running || justFinished || reduceMotion()) { setShown(total); setReplaying(false); return undefined }
    play(total)
    return () => window.clearInterval(timer.current)
  }, [runId, running]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (running) setShown(total) }, [total, running])

  const workingFrame: Frame | null = working ? { active: 'context', done: [], involved: ['context', 'critic'], lit: ['loops'], model: null, hmem: 'idle', revision: false, signals: ['location'], failed: false, finished: false, event: null } : null
  const frame = workingFrame ?? (run ? frameAt(run, shown) : null)
  const words = working ? { title: 'Context Agent is checking…', subtitle: `You are ${Math.round(working.distance)} m from ${working.place}. Asking whether it is worth a ping.`, progress: 0.15 } : caption(run, frame)
  const mode = working ? 'Working' : !run ? '' : run.status === 'running' ? 'Live' : run.provenance === 'recorded' ? 'Recorded replay' : replaying ? 'Replay' : 'Latest run'
  const simulated = Boolean(run?.synthetic_inputs)
  const unresolved = run?.outcome?.locations?.filter((l) => l.status === 'unresolved').length ?? 0

  const live = mode === 'Live'
  return <section className="page orchestra-page">
    <div className="orchestra-top">
      <img className="orchestra-lockup" src="/brand/production/pingo-lockup-transparent.png" alt="pingo" />
      <Link className="orchestra-bell" to="/settings/notifications" aria-label="Notification settings"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a6 6 0 0 0-6 6v3.6L4.5 16v1.5h15V16L18 12.6V9a6 6 0 0 0-6-6Zm-2 16a2 2 0 0 0 4 0h-4Z" /></svg></Link>
    </div>
    <header className="orchestra-head">
      <h1>Agent Activity{mode ? <span className={`orchestra-mode is-${mode.toLowerCase().replace(/ /g, '-')}`}>{live ? <i /> : null}{mode}</span> : null}</h1>
      <p>See how Pingo’s agents work together to turn your screenshots into the right moments.</p>
    </header>
    <div className="orchestra-tabs" role="tablist" aria-label="View">
      <button role="tab" aria-selected={tab === 'orchestra'} onClick={() => setTab('orchestra')}>Orchestra</button>
      <button role="tab" aria-selected={tab === 'trace'} onClick={() => setTab('trace')}>Trace</button>
    </div>

    {sync.busy ? <p className="orchestra-sync" role="status">Syncing screenshot {sync.index} of {sync.total}…</p> : null}
    {sync.error ? <p className="demo-error" role="alert">{sync.error}</p> : null}

    {!run ? <>
      <OrchestraStage frame={null} simulated={false} />
      <div className="trace-peek is-static"><span className="trace-peek-grip" aria-hidden="true" /><strong>Agents are ready</strong><span>Sync a screenshot from <Link to="/">Home</Link> and watch them work.</span></div>
    </> : <>
      <div className="orchestra-meta" hidden={Boolean(working)}>
        <span>{run.label} · {clock(run.started_at)}{simulated ? ' · simulated context' : ''}</span>
        {run.status !== 'running' ? <button onClick={() => play(total)}>↻ Replay</button> : null}
      </div>
      {tab === 'orchestra' ? <>
        <OrchestraStage frame={frame} simulated={simulated} />
        <button className="trace-peek" onClick={() => setTab('trace')} aria-label="Open the full reasoning trace">
          <span className="trace-peek-grip" aria-hidden="true" />
          <strong>{words.title}</strong>
          <span>{words.subtitle}</span>
          {frame?.finished ? <span className="trace-peek-go" aria-hidden="true">→</span> : <span className="trace-peek-bar" role="progressbar" aria-valuenow={Math.round(words.progress * 100)} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${words.progress * 100}%` }} /></span>}
          {unresolved ? <em>{unresolved} place{unresolved === 1 ? ' needs' : 's need'} a location</em> : null}
        </button>
      </> : <div className="trace-view">
        {allRuns.length > 1 ? <label className="trace-pick"><span>Run</span><select value={run.run_id} onChange={(e) => setPicked(e.target.value)}>{allRuns.slice(0, 12).map((r) => <option key={r.run_id} value={r.run_id}>{r.label} · {clock(r.started_at)}</option>)}</select></label> : null}
        {run.outcome?.locations?.length ? <div className="trace-places"><h2>Places</h2><LocationPrompts locations={run.outcome.locations} /></div> : null}
        <TraceTimeline run={run} upTo={run.status === 'running' ? undefined : shown || total} />
        <details className="trace-roles"><summary>Agent roles</summary><ul><li><b>Evidence</b> What is here?</li><li><b>Open Loop</b> What’s unfinished?</li><li><b>Context</b> Why now?</li><li><b>Critic</b> Worth a ping?</li></ul></details>
        <p className="trace-note">Steps are the run’s own recorded events. {run.status === 'running' ? 'This run is still executing.' : run.provenance === 'recorded' ? 'This is a recorded run replayed through the real agents.' : 'This run has finished.'}</p>
      </div>}
    </>}
  </section>
}
