import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { evaluateContext, getContextEntities, getContextEvaluation, getOpenLoopViews } from '../../services/api'
import type { ContextEvaluation, ContextInput } from '../../services/api'
import { wallTime, zonedInstant } from './contextTime'
import { contextPlaces, offsetLocation } from './contextPresets'
import type { VerifiedPlace } from './contextPresets'
import NotificationVisualPreview from '../../features/notifications/NotificationVisualPreview'
import './context.css'

type Mode = 'LOCATION' | 'CALENDAR' | 'TIME'
const initialZone = 'Australia/Melbourne'
export default function ContextSimulator() {
  const [params, setParams] = useSearchParams()
  const agentMode = params.get('mode') === 'agents'
  const [mode, setMode] = useState<Mode>('LOCATION')
  const [zone, setZone] = useState(initialZone)
  const [now, setNow] = useState(() => wallTime(new Date(), initialZone))
  const [lat, setLat] = useState('-37.8000')
  const [lon, setLon] = useState('144.9670')
  const [accuracy, setAccuracy] = useState('20')
  const [label, setLabel] = useState('')
  const [city, setCity] = useState('')
  const [title, setTitle] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [description, setDescription] = useState('')
  const [calendarLat, setCalendarLat] = useState('')
  const [calendarLon, setCalendarLon] = useState('')
  const [pending, setPending] = useState<ContextInput[]>([])
  const [result, setResult] = useState<ContextEvaluation | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [gpsStatus, setGpsStatus] = useState('')
  const [gpsFix, setGpsFix] = useState<{ latitude: number; longitude: number; accuracy: number; timestamp: string } | null>(null)
  const [route, setRoute] = useState('')
  const [step, setStep] = useState(0)
  const [places, setPlaces] = useState<VerifiedPlace[]>([])
  const [unavailable, setUnavailable] = useState<{ entityId: string; name: string; reason: string }[]>([])
  const [loadingPlaces, setLoadingPlaces] = useState(false)
  const [placesLoaded, setPlacesLoaded] = useState(false)
  const [placeError, setPlaceError] = useState('')
  const [selectedPlace, setSelectedPlace] = useState('')
  const [preset, setPreset] = useState<VerifiedPlace | null>(null)
  const savedEvaluation = params.get('evaluation')
  useEffect(() => {
    if (!agentMode || !savedEvaluation || result?.evaluation_id === savedEvaluation) return
    const controller = new AbortController()
    setBusy(true); setError(''); setResult(null)
    getContextEvaluation(savedEvaluation, controller.signal).then(value => {
      if (!controller.signal.aborted) setResult(value)
    }).catch(() => { if (!controller.signal.aborted) setError('This saved evaluation could not be opened. Check the backend connection or evaluation ID.') })
      .finally(() => { if (!controller.signal.aborted) setBusy(false) })
    return () => controller.abort()
  }, [agentMode, savedEvaluation])
  async function loadPlaces() {
    if (loadingPlaces) return
    setLoadingPlaces(true); setPlaceError('')
    try {
      const [entities, loops] = await Promise.all([getContextEntities(), getOpenLoopViews()])
      const data = contextPlaces(entities, loops)
      setPlaces(data.places); setUnavailable(data.unavailable); setPlacesLoaded(true)
      setSelectedPlace(data.places[0]?.entityId ?? '')
    } catch (error) {
      setPlaceError(error instanceof Error && error.message.includes('(404)')
        ? 'This backend does not expose saved-location presets yet. Deploy GET /context-simulator/places; manual context inputs still work.'
        : 'Saved locations could not load. Check the backend connection and retry. No coordinates were guessed.')
    }
    finally { setLoadingPlaces(false) }
  }
  function applyPreset(kind: 'restaurant' | 'far' | 'shopping') {
    const domain = kind === 'shopping' ? 'shopping' : 'food'
    const place = places.find(item => item.entityId === selectedPlace && item.domain === domain) ?? places.find(item => item.domain === domain)
    if (!place) return
    const point = offsetLocation(place.latitude, place.longitude, kind === 'far' ? 4000 : 100)
    setMode('LOCATION'); setLat(point.latitude.toFixed(7)); setLon(point.longitude.toFixed(7)); setAccuracy('20'); setLabel(place.name)
    setPreset(place); setSelectedPlace(place.entityId); setError(''); setResult(null)
  }
  function number(value: string, min: number, max: number, name: string): number {
    const n = Number(value)
    if (!value.trim() || !Number.isFinite(n) || n < min || n > max) throw new Error(`${name} must be between ${min} and ${max}.`)
    return n
  }
  function location(latitude = lat, longitude = lon, name = label) {
    return { latitude: number(latitude, -90, 90, 'Latitude'), longitude: number(longitude, -180, 180, 'Longitude'), name,
      ...(accuracy.trim() ? { accuracy_meters: number(accuracy, 0, 100000, 'Accuracy') } : {}) }
  }
  function stage() {
    setError('')
    try {
      if (pending.length >= 20) throw new Error('Evaluate or reset these events before adding more (maximum 20).')
      const event: ContextInput = { context_id: `ctx_${crypto.randomUUID()}`, source: 'SIMULATED', type: mode, timestamp: zonedInstant(now, zone), timezone: zone }
      if (mode === 'LOCATION') event.location = location()
      if (mode === 'CALENDAR') {
        if (!title.trim()) throw new Error('Enter an event title.')
        event.title = title; event.start_time = zonedInstant(start, zone); event.end_time = zonedInstant(end, zone)
        if (event.end_time <= event.start_time) throw new Error('Event end must be after its start.')
        event.location = calendarLat.trim() || calendarLon.trim() ? { ...location(calendarLat, calendarLon), city } : { name: label, city }; event.description = description
      }
      setPending(items => [...items, event]); setResult(null)
    } catch (e) { setError(e instanceof Error ? e.message : 'Check your fields.') }
  }
  async function run(events: ContextInput[] = pending, instant?: string) {
    if (busy) return
    setError(''); setGpsStatus(''); setBusy(true); setResult(null)
    try {
      if (!events.length) throw new Error('Add a context event first.')
      const response = await evaluateContext(events, instant ?? zonedInstant(now, zone))
      setResult(response)
      if (response.check_in_id) window.dispatchEvent(new Event('recall:data-changed'))
      setParams({ mode: 'agents', evaluation: response.evaluation_id }, { replace: true })
      if (response.notification_id) window.dispatchEvent(new Event('pingo-notifications-changed'))
    } catch (e) { setError(e instanceof Error ? e.message : 'Evaluation could not finish. Check the backend and try again.') }
    finally { setBusy(false) }
  }
  function nearby() {
    if (busy) return
    if (!window.isSecureContext || !navigator.geolocation) { setError('Check Nearby needs HTTPS (or localhost) and browser location support.'); return }
    setBusy(true); setError(''); setResult(null); setGpsFix(null); setGpsStatus('Requesting your location…')
    navigator.geolocation.getCurrentPosition(position => {
      const instant = new Date(position.timestamp).toISOString()
      setGpsFix({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy, timestamp: instant })
      setGpsStatus('Location received. Evaluating nearby saved places…')
      const event: ContextInput = { context_id: `ctx_${crypto.randomUUID()}`, source: 'BROWSER', type: 'LOCATION', timestamp: instant, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        location: { latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy_meters: position.coords.accuracy } }
      // This request contains only the browser observation, never staged simulation inputs.
      evaluateContext([event], instant).then(response => {
        setResult(response); if (response.notification_id) window.dispatchEvent(new Event('pingo-notifications-changed'))
        if (response.check_in_id) window.dispatchEvent(new Event('recall:data-changed'))
        setGpsStatus(response.state === 'FAILED_SAFE' || response.result?.final_action === 'FAILED_SAFE'
          ? 'Evaluation could not finish. No notification was created.'
          : response.notification_id ? 'A relevant ping is available.'
          : response.result?.final_action === 'STAY_SILENT' ? 'Nothing relevant nearby was approved for a notification.'
          : response.result?.final_action === 'ASK' ? 'pingo needs clarification. See the agent decision below.'
          : 'Evaluation finished. See the decision and delivery status below.')
      }).catch(() => {
        setGpsStatus('Location received. The backend could not complete this check.')
        setError('Couldn’t check nearby saved places. Check your connection, Tailscale, and backend availability, then try again.')
      }).finally(() => setBusy(false))
    }, e => {
      setGpsStatus('')
      setError(e.code === 1 ? 'Location permission was denied. Allow location for this site in Safari settings, then try again.'
        : e.code === 3 ? 'Getting your location timed out. Move somewhere with a clearer GPS signal and try again.'
        : 'Your location is unavailable. Check Location Services and your GPS signal, then try again.')
      setBusy(false)
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 })
  }
  function nextLocation() {
    try {
      const rows = route.split('\n').filter(row => row.trim())
      if (step >= rows.length) throw new Error('The route is finished. Edit it to start another sequence.')
      const [latitude, longitude, ...name] = rows[step].split(',').map(s => s.trim())
      const event: ContextInput = { context_id: `ctx_${crypto.randomUUID()}`, source: 'SIMULATED', type: 'LOCATION', timestamp: zonedInstant(now, zone), timezone: zone, location: location(latitude, longitude, name.join(', ')) }
      setStep(step + 1); void run([event])
    } catch (e) { setError(e instanceof Error ? e.message : 'Use latitude, longitude, label on each line.') }
  }
  return <section className="page context-simulator">
    <Link className="back-link" to="/">Back to Home</Link>
    <header className="page-header"><h1>Context Simulator</h1><p>Test when pingo should speak up — and when it should stay quiet.</p></header>
    <div className="context-test-modes" role="group" aria-label="Testing mode">
      <button type="button" disabled={busy} aria-pressed={!agentMode} onClick={() => setParams({})}>Visual preview</button>
      <button type="button" disabled={busy} aria-pressed={agentMode} onClick={() => setParams({ mode: 'agents' })}>Real agent evaluation</button>
    </div>
    {!agentMode ? <NotificationVisualPreview /> : <>
    <p className="context-disclosure"><strong>Real agent evaluation.</strong> Synthetic inputs are stored and evaluated against your saved intentions through Nightshift. This can create real notifications and cooldowns. Sample mode cannot run it.</p>
    <section className="context-presets" aria-labelledby="context-presets-heading"><h2 id="context-presets-heading">Saved location presets</h2>
      <p>Use verified coordinates from your saved entities. Presets fill the form; only Run agent evaluation calls the agents.</p>
      <small>Location search: © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>, via Nominatim. Uncertain places remain unlocated.</small>
      <button type="button" className="context-secondary" disabled={loadingPlaces || busy} onClick={() => void loadPlaces()}>{loadingPlaces ? 'Loading saved locations…' : placesLoaded ? 'Refresh saved locations' : 'Load saved locations'}</button>
      {placeError && <p role="alert" className="context-error">{placeError}</p>}
      {places.length > 0 && <label>Saved place<select value={selectedPlace} onChange={event => setSelectedPlace(event.target.value)} disabled={busy}>{places.map(place => <option key={place.entityId} value={place.entityId}>{place.name} · {place.domain === 'shopping' ? 'verified store association' : place.domain}</option>)}</select></label>}
      <div className="context-actions">
        <button type="button" className="context-secondary" disabled={busy || !places.some(place => place.domain === 'food')} onClick={() => applyPreset('restaurant')}>Near saved restaurant</button>
        <button type="button" className="context-secondary" disabled={busy || !places.some(place => place.domain === 'food')} onClick={() => applyPreset('far')}>Far from saved restaurant</button>
        <button type="button" className="context-secondary" disabled={busy || !places.some(place => place.domain === 'shopping')} onClick={() => applyPreset('shopping')}>Near saved shopping location</button>
      </div>
      {placesLoaded && !places.length && <p>No saved places have both verified coordinates and an active, evidence-backed intention. Proximity presets are unavailable.</p>}
      {preset && <details><summary>Preset source · {preset.name}</summary><p>100 m nearby or 4 km away from {preset.latitude}, {preset.longitude}. Other nearby places may still be relevant at the far point. Changing coordinates below overrides this preset.</p><p>Coordinate source: {preset.source}</p><p>Entity: {preset.entityId} · Linked intentions: {preset.loopIds.join(', ')} · Evidence: {preset.evidenceIds.join(', ')}</p><small>Store association does not establish product availability. Final eligibility and interruption are decided by the existing workflow.</small></details>}
      {unavailable.length > 0 && <details><summary>{unavailable.length} saved entities unavailable for proximity</summary><ul>{unavailable.map(item => <li key={item.entityId}><strong>{item.name}</strong>: {item.reason}</li>)}</ul></details>}
    </section>
    <section className="context-clock" aria-label="Evaluation clock">
      <label>Current date and time<input type="datetime-local" value={now} onChange={e => setNow(e.target.value)} disabled={busy} /></label>
      <label>Timezone<input value={zone} onChange={e => setZone(e.target.value)} disabled={busy} placeholder="Australia/Melbourne" /></label>
    </section>
    <div className="context-tabs" role="group" aria-label="Context type">
      {(['LOCATION', 'CALENDAR', 'TIME'] as const).map(item => <button type="button" key={item} aria-pressed={mode === item} disabled={busy} onClick={() => setMode(item)}>{item === 'LOCATION' ? 'Location' : item === 'CALENDAR' ? 'Calendar' : 'Time'}</button>)}
    </div>
    <form className="context-form" onSubmit={e => { e.preventDefault(); stage() }}>
      <h2>{mode === 'LOCATION' ? 'Simulate a location' : mode === 'CALENDAR' ? 'Simulate a calendar event' : 'Simulate time'}</h2>
      {mode === 'LOCATION' && <>
        <div className="context-fields"><label>Latitude<input type="number" step="any" min="-90" max="90" required value={lat} onChange={e => setLat(e.target.value)} disabled={busy} /></label>
        <label>Longitude<input type="number" step="any" min="-180" max="180" required value={lon} onChange={e => setLon(e.target.value)} disabled={busy} /></label></div>
        <label>Accuracy radius in metres (optional)<input type="number" min="0" max="100000" value={accuracy} onChange={e => setAccuracy(e.target.value)} disabled={busy} /></label>
      </>}
      {mode === 'CALENDAR' && <>
        <label>Event title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} disabled={busy} placeholder="Lunch with Sarah" /></label>
        <div className="context-fields"><label>Start<input type="datetime-local" required value={start} onChange={e => setStart(e.target.value)} disabled={busy} /></label>
        <label>End<input type="datetime-local" required value={end} onChange={e => setEnd(e.target.value)} disabled={busy} /></label></div>
        <label>Description (optional)<textarea maxLength={1000} value={description} onChange={e => setDescription(e.target.value)} disabled={busy} /></label>
        <label>City (optional)<input maxLength={100} value={city} onChange={event => setCity(event.target.value)} disabled={busy} placeholder="Melbourne" /></label>
        <div className="context-fields"><label>Event latitude (optional)<input type="number" step="any" value={calendarLat} onChange={e => setCalendarLat(e.target.value)} disabled={busy} /></label><label>Event longitude (optional)<input type="number" step="any" value={calendarLon} onChange={e => setCalendarLon(e.target.value)} disabled={busy} /></label></div>
      </>}
      {mode !== 'TIME' && <label>Location label (optional)<input maxLength={200} value={label} onChange={e => setLabel(e.target.value)} disabled={busy} placeholder="Carlton, Melbourne" /></label>}
      {mode === 'TIME' && <p>The evaluation clock above is your synthetic current time. Previously submitted calendar events within 14 days can be reconsidered.</p>}
      <button className="context-secondary" type="submit" disabled={busy}>Simulate {mode === 'LOCATION' ? 'Location' : mode === 'CALENDAR' ? 'Calendar Event' : 'Time'}</button>
    </form>
    <section className="context-queue" aria-label="Staged context">
      <h2>Ready to evaluate · {pending.length}</h2>
      {!pending.length ? <p>Add a simulated event above. No agent call happens until you run evaluation.</p> : <ul>{pending.map(event => <li key={event.context_id}>{event.type} · {event.title || event.location?.name || event.timestamp} <button type="button" disabled={busy} onClick={() => setPending(items => items.filter(i => i.context_id !== event.context_id))} aria-label={`Remove ${event.type} event`}>Remove</button></li>)}</ul>}
      <div className="context-actions"><button className="context-primary" disabled={busy || !pending.length} onClick={() => void run()}>{busy ? 'Evaluating with agents…' : 'Run agent evaluation'}</button>
      <button className="context-secondary" disabled={busy} onClick={() => { setPending([]); setResult(null); setError(''); setGpsStatus(''); setGpsFix(null); setPreset(null); setRoute(''); setStep(0) }}>Reset Simulation</button></div>
      <small>Reset clears this panel. It does not delete stored context, feedback, or cooldowns.</small>
    </section>
    <details className="context-movement"><summary>Simulate movement</summary><label>One latitude, longitude, optional label per line<textarea rows={4} value={route} disabled={busy} onChange={e => { setRoute(e.target.value); setStep(0) }} placeholder={'-37.8136, 144.9631, Melbourne CBD\n-37.8000, 144.9670, Carlton'} /></label><button type="button" className="context-secondary" disabled={busy || !route.trim()} onClick={nextLocation}>Next Location · {step + 1}</button><p>Each step runs separately. Repeat a location to test cooldown.</p></details>
    <section className="context-live"><h2>Check Nearby</h2><p>Use your current location to check saved places. Keep pingo open while the agents evaluate.</p><button type="button" className="context-secondary" onClick={nearby} disabled={busy}>Check Nearby</button><small>Requires HTTPS and your permission. Nothing is tracked in the background; staged simulations are excluded.</small>
      {gpsStatus && <p role="status">{gpsStatus}</p>}
      {gpsFix && <details><summary>Location received · accuracy ±{Math.round(gpsFix.accuracy)} m</summary><p>{gpsFix.latitude.toFixed(6)}, {gpsFix.longitude.toFixed(6)} · {new Date(gpsFix.timestamp).toLocaleString()}</p><small>Live browser observation. These coordinates are submitted only when you press Check Nearby.</small></details>}
    </section>
    {error && <p role="alert" className="context-error">{error}</p>}
    {busy && !gpsStatus && <p role="status">The agents are evaluating. You can leave this tab open; polling never triggers more reasoning.</p>}
    {result && <section className="context-result" aria-live="polite"><h2>{result.result?.final_action ?? result.state}</h2>
      {savedEvaluation && <small>Stored evaluation. Viewing this result does not call the agents again.</small>}
      <p>{result.error || (result.result?.final_action === 'STAY_SILENT' ? 'No notification was approved.' : result.delivery === 'APPROVED_PENDING_DELIVERY' ? 'Approved. Waiting for the open app to acknowledge delivery.' : result.delivery === 'NOT_APPROVED' ? 'No notification was approved.' : `Delivery: ${result.delivery}`)}</p>
      <p className="pingo-source">{result.source.join(', ')} context{result.replayed ? ' · Saved result, no new agent calls' : ''}</p>
      {result.notification_id && <Link className="context-primary" to={`/recalls/${result.notification_id}`}>Open approved ping</Link>}
      {result.check_in_id && <Link className="context-primary" to="/check-in">Answer Pingo’s question</Link>}
      {result.check_in_error && <p role="alert">{result.check_in_error}</p>}
      {result.result?.question && <p><strong>Clarification requested:</strong> {result.result.question} <span>The current Check-in contract does not accept context answers yet.</span></p>}
      <h3>Candidate intentions</h3>
      {!result.candidates?.length ? <p>No eligible evidence-backed intentions were found.</p> : <ul className="context-candidates">{result.candidates.map(c => <li key={c.loop_id}><strong>{c.title}</strong><span>{c.eligible ? 'Offered to Context Agent' : `Excluded: ${c.exclusion?.replaceAll('_', ' ')}`}</span>{c.geography.map((g, i) => <small key={`${g.entity_id}-${i}`}>{g.entity_id}: {g.match}{g.distance_meters === null ? ' · no verified distance' : ` · ${g.distance_meters} m`}</small>)}</li>)}</ul>}
      <h3>Agent decisions</h3><ol className="context-trace">{result.result?.trace_events.map((t, i) => <li key={i}><strong>{t.agent} · {t.action}</strong><p>{t.reason}</p>{t.receipt && <small>{t.receipt.provider} · {t.receipt.routed_model}</small>}</li>)}</ol>
      {result.result?.error && <p className="context-error">{result.result.error}</p>}
      <details><summary>Submitted context and trace identifiers</summary><pre>{JSON.stringify({ evaluation_id: result.evaluation_id, run_id: result.result?.run_id, inputs: result.submitted_context }, null, 2)}</pre></details>
    </section>}
    </>}
  </section>
}
