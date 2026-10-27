import { useEffect, useState } from 'react'
import { deleteScreenshot, getHealth } from '../../services/runsApi'
import './delete-intention.css'

/** A small × on a saved screenshot. Two taps (the first asks). The screenshot is hidden, stays stored (Evidence is append-only), and can be synced again. */
export default function DeleteScreenshot({ evidenceId }: { evidenceId: string }) {
  const [allowed, setAllowed] = useState(false)
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then((h) => setAllowed(h.mode === 'real' || h.mode === 'demo' || (h.mode === 'sample' && !!h.live_models))).catch(() => setAllowed(false))
    return () => controller.abort()
  }, [])
  if (!allowed) return null
  const remove = async () => {
    setBusy(true)
    try { await deleteScreenshot(evidenceId); window.dispatchEvent(new Event('recall:data-changed')) } catch { setBusy(false); setArmed(false) }
  }
  return armed
    ? <span className="shot-delete is-armed"><button type="button" disabled={busy} onClick={() => void remove()}>{busy ? '…' : 'Delete'}</button><button type="button" disabled={busy} onClick={() => setArmed(false)} aria-label="Keep this screenshot">Keep</button></span>
    : <button type="button" className="shot-delete" aria-label="Delete this screenshot" onClick={() => setArmed(true)}>×</button>
}
