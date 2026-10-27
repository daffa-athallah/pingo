import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getNotifications } from '../../services/api'
import type { PingoNotification } from '../../services/api'
import HomePage from '../../pages/home/HomePage'
import { NoticeCard } from './NotificationCenter'
import NotificationDetail from './NotificationDetail'
import NotificationVisualPreview from './NotificationVisualPreview'
import './notifications.css'

/** Developer-only display replay: read saved content; never acknowledge delivery, request OS permission or submit feedback. */
function SavedNotificationPreview() {
  const [notice, setNotice] = useState<PingoNotification | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [show, setShow] = useState(false)
  const [detail, setDetail] = useState(false)
  const [animation, setAnimation] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    getNotifications(controller.signal).then(values => {
      if (!controller.signal.aborted) setNotice(values[0] ?? null)
    }).catch(() => {
      if (!controller.signal.aborted) setError('Couldn’t load a saved notification. Check the backend connection and retry.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [revision])

  return <>
    {detail && notice ? <NotificationDetail key={animation} previewNotice={notice} /> : <HomePage />}
    {show && notice && <aside className="pingo-notices" aria-label="Notification UI preview" aria-live="polite">
      <NoticeCard key={animation} notice={notice} onPreviewOpen={() => { setShow(false); setDetail(true); window.scrollTo(0, 0) }} />
    </aside>}
    <section className="notification-preview-controls" aria-label="Notification preview controls">
      <div><strong>Notification UI preview</strong><p>{loading ? 'Loading saved notification…' : error || (!notice ? 'No saved notification is available to preview yet.' : 'Replays saved content. No agent calls or changes saved.')}</p></div>
      <div className="notification-preview-actions">
        {error ? <button type="button" onClick={() => setRevision(value => value + 1)}>Retry</button>
          : <button type="button" disabled={loading || !notice} onClick={() => { setDetail(false); setShow(true); setAnimation(value => value + 1); window.scrollTo(0, 0) }}>Show notification</button>}
        {show && <button type="button" className="preview-secondary" onClick={() => setShow(false)}>Hide</button>}
        <Link to="/">Exit preview</Link>
      </div>
    </section>
  </>
}

export default function NotificationPreview() {
  const [params] = useSearchParams()
  if (params.get('saved') === 'true') return <SavedNotificationPreview />
  return <section className="page context-simulator"><Link className="back-link" to="/context-simulator">Back to Context Simulator</Link>
    <NotificationVisualPreview />
    <Link className="back-link" to="?saved=true">Replay a stored notification instead</Link>
  </section>
}
