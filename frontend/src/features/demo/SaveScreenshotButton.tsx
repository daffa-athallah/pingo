import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getHealth } from '../../services/runsApi'
import type { Health } from '../../services/runsApi'
import { startSync, useSync } from '../orchestra/syncStore'
import './save-button.css'

/** Sync from Home: pick screenshots, confirm once if they go into the real (permanent) history, then follow the agents on Agent Activity.
 *  Shown wherever uploading works: the real backend, the resettable demo workspace, or sample with live models. */
export default function SaveScreenshotButton() {
  const [health, setHealth] = useState<Health | null>(null)
  const [pending, setPending] = useState<File[] | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const sync = useSync()
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(setHealth).catch(() => setHealth(null))
    return () => controller.abort()
  }, [])
  const allowed = health && (health.mode === 'real' || health.mode === 'demo' || (health.mode === 'sample' && !!health.live_models))
  if (!allowed) return null
  const go = (files: File[]) => { void startSync(files); navigate('/agent-activity') }
  return <>
    <button type="button" className="save-screenshot-button" disabled={sync.busy} onClick={() => input.current?.click()} aria-label="Sync screenshots">
      <span aria-hidden="true">+</span> {sync.busy ? `Syncing ${sync.index}/${sync.total}` : 'Sync screenshots'}
    </button>
    <input ref={input} type="file" multiple accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => {
      const files = Array.from(e.target.files ?? []); e.target.value = ''
      if (!files.length) return
      if (health?.mode === 'real') setPending(files); else go(files)
    }} />
    {pending ? <div className="sync-confirm" role="dialog" aria-modal="true" aria-label="Add to your saved history">
      <div>
        <h2>Add {pending.length} screenshot{pending.length === 1 ? '' : 's'}?</h2>
        <p>They go to your real saved history in Zetaris and cannot be edited or deleted afterwards. The agents will analyse them through Nightshift.</p>
        <div><button type="button" className="demo-button is-quiet" onClick={() => setPending(null)}>Cancel</button>
          <button type="button" className="demo-button" onClick={() => { const files = pending; setPending(null); go(files) }}>Sync</button></div>
      </div>
    </div> : null}
  </>
}
