import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getHealth, deleteIntention } from '../../services/runsApi'
import './delete-intention.css'

/** Remove an intention from Pingo (two taps). The saved Evidence stays in Zetaris (append-only) but is no longer shown, and the same screenshots can be synced again. */
export default function DeleteIntention({ loopId, name }: { loopId: string; name: string }) {
  const [allowed, setAllowed] = useState(false)
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then((h) => setAllowed(h.mode === 'real' || h.mode === 'demo' || (h.mode === 'sample' && !!h.live_models))).catch(() => setAllowed(false))
    return () => controller.abort()
  }, [])
  if (!allowed) return null
  const remove = async () => {
    setBusy(true); setError('')
    try {
      await deleteIntention(loopId)
      window.dispatchEvent(new Event('recall:data-changed'))
      navigate('/')
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not delete.'); setBusy(false) }
  }
  return <div className="delete-intention">
    {armed
      ? <><p>Delete “{name}”? Its reminders stop and it disappears from Home. The screenshots stay stored, but are hidden, and can be synced again.</p>
        <div><button type="button" className="demo-button is-quiet" disabled={busy} onClick={() => setArmed(false)}>Keep it</button>
          <button type="button" className="delete-confirm" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete'}</button></div></>
      : <button type="button" className="delete-link" onClick={() => setArmed(true)}>Delete this intention</button>}
    {error ? <p className="demo-error" role="alert">{error}</p> : null}
  </div>
}
