import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../../services/api'
import { getHealth, getRunRecord, resetDemo, startUpload } from '../../services/runsApi'
import type { Health, RunRecord } from '../../services/runsApi'
import './demo.css'

// A plain page to record the live demo: save a screenshot, watch the agents work, see what changed. Product screens belong to the app UI.
const STEP_LABEL: Record<string, string> = { UPLOAD: 'Upload', EVIDENCE: 'Evidence Agent', REPOSITORY: 'Demo workspace', ZETARIS: 'Zetaris', OPEN_LOOP: 'Open Loop Agent', RUN: 'Run' }

export default function DemoUpload() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [run, setRun] = useState<RunRecord | null>(null)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    getHealth().then(setHealth).catch((e: unknown) => setError(e instanceof Error ? e.message : 'The backend is not reachable.'))
    return () => window.clearInterval(timer.current)
  }, [])

  const watch = (runId: string) => {
    window.clearInterval(timer.current)
    timer.current = window.setInterval(async () => {
      try {
        const next = await getRunRecord(runId)
        setRun(next)
        if (next.status !== 'running') { window.clearInterval(timer.current); setBusy(false) }
      } catch (e) {
        window.clearInterval(timer.current); setBusy(false); setError(e instanceof Error ? e.message : 'Lost contact with the backend.')
      }
    }, 700)
  }

  const upload = async (file: File | undefined) => {
    if (!file) return
    setError(null); setRun(null); setBusy(true)
    try {
      const started = await startUpload(file)
      setRun(await getRunRecord(started.run_id))
      if (started.status === 'running') watch(started.run_id); else setBusy(false)
    } catch (e) {
      setBusy(false); setError(e instanceof Error ? e.message : 'Upload failed.')
    }
  }

  const reset = async () => {
    setError(null); setRun(null)
    try { await resetDemo() } catch (e) { setError(e instanceof Error ? e.message : 'Reset failed.') }
  }

  const demoWorkspace = health?.mode === 'demo'
  const events = run?.result.trace_events ?? []
  const outcome = run?.outcome
  return (
    <section className="page demo-page">
      <header>
        <h1>Save a screenshot</h1>
        {health ? (demoWorkspace
          ? <p className="demo-badge is-demo">Demo workspace · in-memory copy of the saved history · resettable · real models</p>
          : <p className="demo-badge is-warn">This is the {health.workspace} workspace. Uploads here are permanent, so this page is disabled. Start the backend with <code>serve.py --demo</code>.</p>)
          : <p className="demo-badge">{error ?? 'Connecting to the backend…'} ({API_BASE_URL})</p>}
      </header>

      <div className="demo-actions">
        <label className={`demo-button${!demoWorkspace || busy ? ' is-disabled' : ''}`}>
          {busy ? 'Working…' : 'Choose a screenshot'}
          <input type="file" accept="image/png,image/jpeg,image/webp" disabled={!demoWorkspace || busy} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        <button type="button" className="demo-button is-quiet" disabled={!demoWorkspace || busy} onClick={() => void reset()}>Reset workspace</button>
      </div>
      {error && health ? <p className="demo-error" role="alert">{error}</p> : null}

      {run ? (
        <>
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
              <p className="demo-links">
                <Link to={`/agent-activity?demo=${run.run_id}`}>Open in Agent Activity</Link>
                <Link to="/">Back to Home</Link>
              </p>
            </div>
          ) : null}
          {run.status === 'failed' ? <p className="demo-error" role="alert">{run.result.error ?? 'The screenshot could not be processed. Nothing was stored.'}</p> : null}
        </>
      ) : null}
    </section>
  )
}
