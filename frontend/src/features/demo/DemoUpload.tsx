import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API_BASE_URL } from '../../services/api'
import { getHealth, getRunRecord, resetDemo, resetSample, startUpload } from '../../services/runsApi'
import type { Health, RunRecord } from '../../services/runsApi'
import LocationPrompts from './LocationPrompts'
import PipelineFlow from './PipelineFlow'
import './demo.css'

// A plain page to record the live demo: save a screenshot, watch the agents work, see what changed. Product screens belong to the app UI.
const STEP_LABEL: Record<string, string> = { LOCATION: 'Location', UPLOAD: 'Upload', EVIDENCE: 'Evidence Agent', REPOSITORY: 'Demo workspace', ZETARIS: 'Zetaris', OPEN_LOOP: 'Open Loop Agent', RUN: 'Run' }

export default function DemoUpload() {
  const navigate = useNavigate()
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmed, setConfirmed] = useState(false)  // real data is permanent, so uploading there needs an explicit yes
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    getHealth().then((value) => { if (value.mode === 'sample' && !value.live_models) navigate('/?guide=1', { replace: true }); else setHealth(value) }).catch((e: unknown) => setError(e instanceof Error ? e.message : 'The backend is not reachable.'))
    return () => window.clearInterval(timer.current)
  }, [navigate])

  const [queue, setQueue] = useState<{ index: number; total: number } | null>(null)

  // A slow poll must not abandon the run: it keeps going on the server, so keep asking (for up to 15 minutes) and ignore a timed-out request.
  const finish = async (runId: string) => {
    const deadline = Date.now() + 15 * 60_000
    while (Date.now() < deadline) {
      try {
        const next = await getRunRecord(runId)
        setRun(next)
        if (next.status !== 'running') return next
      } catch { /* the server is busy; ask again */ }
      await new Promise((resolve) => window.setTimeout(resolve, 1500))
    }
    throw new Error('Still working after 15 minutes. Check Home later; the screenshot may have been saved.')
  }

  /** One screenshot at a time (the store has a single writer), in the order they were picked. */
  const upload = async (files: File[]) => {
    if (!files.length) return
    setError(null); setRun(null); setBusy(true)
    try {
      for (const [index, file] of files.entries()) {
        setQueue({ index: index + 1, total: files.length })
        const started = await startUpload(file)
        setRun(await getRunRecord(started.run_id))
        if (started.status === 'running') await finish(started.run_id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed.')
    } finally { setBusy(false); setQueue(null) }
  }

  const reset = async () => {
    setError(null); setRun(null)
    try { await (health?.mode === 'sample' ? resetSample() : resetDemo()) } catch (e) { setError(e instanceof Error ? e.message : 'Reset failed.') }
  }

  const realData = health?.mode === 'real'
  const demoWorkspace = health?.mode === 'demo' || (health?.mode === 'sample' && !!health.live_models)
  const canUpload = demoWorkspace || (realData && confirmed)
  const events = run?.result.trace_events ?? []
  const outcome = run?.outcome
  return (
    <section className="page demo-page">
      <header>
        <h1>Sync screenshots</h1>
        {health ? (demoWorkspace
          ? <p className="demo-badge is-demo">Demo workspace · in-memory copy of the saved history · resettable · real models</p>
          : realData
            ? <p className="demo-badge is-warn">Real data · saved permanently to Zetaris · analysed by the agents through Nightshift. Evidence cannot be edited or deleted afterwards.</p>
            : <p className="demo-badge is-warn">This is the {health.workspace} workspace without live models. Start the backend with <code>serve.py --demo</code>.</p>)
          : <p className="demo-badge">{error ?? 'Connecting to the backend…'} ({API_BASE_URL})</p>}
      </header>

      {realData ? <label className="demo-confirm"><input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} /> I understand this adds to my real saved history.</label> : null}
      <div className="demo-actions">
        <label className={`demo-button${!canUpload || busy ? ' is-disabled' : ''}`}>
          {busy ? (queue && queue.total > 1 ? `Working… ${queue.index} of ${queue.total}` : 'Working…') : 'Choose screenshots'}
          <input type="file" multiple accept="image/png,image/jpeg,image/webp" disabled={!canUpload || busy} onChange={(e) => { void upload(Array.from(e.target.files ?? [])); e.target.value = '' }} />
        </label>
        {realData ? null : <button type="button" className="demo-button is-quiet" disabled={!demoWorkspace || busy} onClick={() => void reset()}>Reset workspace</button>}
      </div>
      {error && health ? <p className="demo-error" role="alert">{error}</p> : null}

      <PipelineFlow events={events} running={busy || run?.status === 'running'} done={run?.status === 'done' && !busy} />
      <p className="demo-note">On the web you choose screenshots from Photos (open the Screenshots album and select several). A native app could sync that album automatically.</p>

      {run ? (
        <>
          {run.provenance === 'recorded' ? <p className="demo-badge">Recorded real run, replayed. Receipts describe the original capture. Each case uses an isolated snapshot.</p> : null}
          {run.check_ins?.map((question) => <p key={question.id}><strong>Check-in:</strong> {question.question}</p>)}
          <ol className="demo-steps" aria-live="polite">
            {events.map((event) => (
              <li key={event.seq ?? `${event.agent}-${event.action}`} className={`is-${event.agent.toLowerCase()}`}>
                <span className="demo-step-agent">{STEP_LABEL[event.agent] ?? event.agent}</span>
                <span className="demo-step-action">{event.action.replace('_', ' ')}</span>
                <span className="demo-step-reason">{event.reason}</span>
                {event.receipt ? <span className="demo-step-receipt">{event.receipt.routed_model} via {event.receipt.provider}</span> : null}
              </li>
            ))}
            {run.status === 'running' ? <li className="demo-working"><span className="demo-dot" />Working…</li> : null}
          </ol>

          {outcome ? (
            <div className="demo-outcome">
              {outcome.evidence ? (outcome.evidence.sensitive
                ? <p><strong>Saved, not analysed.</strong> The screenshot was flagged as sensitive, so nothing about it is shown and no reasoning model saw it.</p>
                : <p><strong>Understood:</strong> {outcome.evidence.summary}</p>) : null}
              {outcome.open_loop.loop ? (
                <p><strong>{outcome.open_loop.decision}</strong> → “{outcome.open_loop.loop.title}”
                  {outcome.open_loop.change ? ` · ${outcome.open_loop.change.change}` : ''}</p>
              ) : null}
              <LocationPrompts locations={outcome.locations} />
              <p className="demo-links">
                <Link to={`/agent-activity?demo=${run.run_id}`}>Open in Agent Activity</Link>
                <Link to="/">Back to Home</Link>
              </p>
            </div>
          ) : null}
          {!outcome ? <p><Link to={`/agent-activity?demo=${run.run_id}`}>Open in Agent Activity</Link> · {run.result.final_action}</p> : null}
          {run.status === 'failed' ? <p className="demo-error" role="alert">{run.result.error ?? 'The screenshot could not be processed. Nothing was stored.'}</p> : null}
        </>
      ) : null}
    </section>
  )
}
