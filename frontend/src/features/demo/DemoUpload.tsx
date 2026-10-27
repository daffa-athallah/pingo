import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { API_BASE_URL } from '../../services/api'
import { getHealth, getRunRecord, resetDemo, resetSample, setEntityLocation, startUpload } from '../../services/runsApi'
import type { Health, RunRecord } from '../../services/runsApi'
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
  const [pins, setPins] = useState<Record<string, string>>({})
  const [pinned, setPinned] = useState<Record<string, string>>({})
  const [pinError, setPinError] = useState<Record<string, string>>({})
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    getHealth().then((value) => { if (value.mode === 'sample' && !value.live_models) navigate('/?guide=1', { replace: true }); else setHealth(value) }).catch((e: unknown) => setError(e instanceof Error ? e.message : 'The backend is not reachable.'))
    return () => window.clearInterval(timer.current)
  }, [navigate])

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
        <h1>{realData ? 'Add a screenshot' : 'Save a screenshot'}</h1>
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
          {busy ? 'Working…' : 'Choose a screenshot'}
          <input type="file" accept="image/png,image/jpeg,image/webp" disabled={!canUpload || busy} onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = '' }} />
        </label>
        {realData ? null : <button type="button" className="demo-button is-quiet" disabled={!demoWorkspace || busy} onClick={() => void reset()}>Reset workspace</button>}
      </div>
      {error && health ? <p className="demo-error" role="alert">{error}</p> : null}

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
              {outcome.locations?.map((place) => (
                <div key={place.entity_id} className="demo-location">
                  {place.status === 'unresolved' ? (
                    <>
                      <p><strong>{place.name}</strong>: the map has no match, so nearby reminders are off for it. Paste a Google Maps link (or “lat, lon”) to turn them on.</p>
                      {pinned[place.entity_id] ? <p className="demo-ok">Saved: {pinned[place.entity_id]}</p> : (
                        <form onSubmit={async (e) => { e.preventDefault(); setPinError((v) => ({ ...v, [place.entity_id]: '' })); try { const r = await setEntityLocation(place.entity_id, pins[place.entity_id] ?? ''); setPinned((v) => ({ ...v, [place.entity_id]: `${r.latitude.toFixed(5)}, ${r.longitude.toFixed(5)}` })) } catch (err) { setPinError((v) => ({ ...v, [place.entity_id]: err instanceof Error ? err.message : 'Could not save.' })) } }}>
                          <input value={pins[place.entity_id] ?? ''} onChange={(e) => setPins((v) => ({ ...v, [place.entity_id]: e.target.value }))} placeholder="https://maps.app.goo.gl/… or -37.9187, 145.1286" aria-label={`Location of ${place.name}`} />
                          <button type="submit" className="demo-button is-quiet">Save location</button>
                          {pinError[place.entity_id] ? <span className="demo-error" role="alert">{pinError[place.entity_id]}</span> : null}
                        </form>)}
                    </>
                  ) : <p><strong>{place.name}</strong>: located at {Number(place.latitude).toFixed(5)}, {Number(place.longitude).toFixed(5)} ({place.status === 'resolved' ? 'found on the map' : 'already saved'}). Nearby reminders are on.</p>}
                </div>
              ))}
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
