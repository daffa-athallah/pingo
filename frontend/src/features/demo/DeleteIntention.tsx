import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getHealth, deleteIntention } from '../../services/runsApi'
import './delete-intention.css'

/** Delete an intention and all its screenshots (two taps). Uploaded image files are erased; the append-only Zetaris records stay but are hidden. The same images can be synced again. */
export default function DeleteIntention({ loopId, name, count }: { loopId: string; name: string; count: number }) {
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
      ? <><p>Delete “{name}” and {count === 1 ? 'its screenshot' : `all ${count} of its screenshots`}? Its reminders stop and it disappears from Home. The images you uploaded are erased from this computer. Pingo’s text notes about them stay in Zetaris (it is append-only), hidden. You can sync them again.</p>
        <div><button type="button" className="demo-button is-quiet" disabled={busy} onClick={() => setArmed(false)}>Keep it</button>
          <button type="button" className="delete-confirm" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete'}</button></div></>
      : <button type="button" className="delete-link" onClick={() => setArmed(true)}>Delete this intention</button>}
    {error ? <p className="demo-error" role="alert">{error}</p> : null}
  </div>
}
