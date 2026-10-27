import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { actOnNotification, getNotification, imageUrl } from '../../services/api'
import type { NoticeAction, PingoNotification } from '../../services/api'
import './notifications.css'

export default function NotificationDetail({ previewNotice }: { previewNotice?: PingoNotification } = {}) {
  const { notificationId = '' } = useParams()
  const [notice, setNotice] = useState<PingoNotification | null>(previewNotice ?? null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState('')
  useEffect(() => {
    if (previewNotice) { setNotice(previewNotice); setFeedback(''); setError(''); return }
    const controller = new AbortController()
    setNotice(null); setFeedback(''); setError('')
    getNotification(notificationId, controller.signal).then(async n => {
      if (controller.signal.aborted) return
      setNotice(n)
      await actOnNotification(notificationId, 'DELIVERED')
      await actOnNotification(notificationId, 'READ')
      window.dispatchEvent(new Event('pingo-notifications-changed'))
    }).catch(() => { if (!controller.signal.aborted) setError('This ping could not be opened. It may have been dismissed or its intention completed.') })
    return () => controller.abort()
  }, [notificationId, previewNotice])
  async function action(value: NoticeAction) {
    if (busy) return
    if (previewNotice) {
      const label = { DONE: 'Done', SNOOZE: 'Snooze', DISMISS: 'Dismiss', NOT_RELEVANT: 'Not relevant', JUST_INSPIRATION: 'Just inspiration', READ: 'Read', DELIVERED: 'Delivered' }[value]
      setFeedback(`Preview: “${label}” selected. No changes were saved.`)
      return
    }
    setBusy(true); setError('')
    try {
      await actOnNotification(notificationId, value)
      setFeedback(value === 'DONE' ? 'Done. This intention is now completed.' : value === 'SNOOZE' ? 'Snoozed for a day.' : value === 'DISMISS' ? 'Ping dismissed.' : 'Feedback saved. We will stop reminders for this intention.')
      window.dispatchEvent(new Event('pingo-notifications-changed'))
    } catch (e) { setError(e instanceof Error ? e.message : 'Feedback could not be saved. Try again.') }
    finally { setBusy(false) }
  }
  return <section className="page pingo-recall-detail">
    <Link className="back-link" to="/">Back to Home</Link>
    {error && <p role="alert">{error}</p>}
    {!notice && !error && <p role="status">Loading ping…</p>}
    {notice && <>
      <header className="page-header pingo-recall-header"><span>Timely ping</span><h1>{notice.payload.title}</h1><p>{notice.payload.message}</p></header>
      <p className="pingo-source">{notice.payload.sources.join(', ')} context · {notice.payload.trigger_types.join(', ')} · {new Date(notice.created_at).toLocaleString()}</p>
      <section className="pingo-why-now"><h2>Why now?</h2><p>{notice.payload.reason}</p></section>
      <Link className="context-primary" to={`/entity/${encodeURIComponent(notice.loop_id)}`}>View saved intention</Link>
      <section><h2>Evidence from your screenshots</h2><div className="pingo-evidence">
        {notice.payload.evidence.map(e => <figure key={e.evidence_id}>
          {e.image_url && <a href={imageUrl(e.image_url, 1600)} target="_blank" rel="noreferrer"><img src={imageUrl(e.image_url, 400)} alt={e.summary} loading="lazy" /></a>}
          <figcaption>{e.summary}</figcaption>
        </figure>)}
      </div></section>
      <p className="pingo-connected">Connected to: {notice.payload.entities.map(e => e.name).join(', ')}</p>
      {feedback ? <p role="status">{feedback} <Link to="/">Back to Home</Link></p> : <div className="pingo-feedback" aria-label="Ping feedback">
        {([['DONE', 'Done'], ['SNOOZE', 'Snooze'], ['NOT_RELEVANT', 'Not relevant'], ['JUST_INSPIRATION', 'Just inspiration'], ['DISMISS', 'Dismiss']] as const).map(([value, label]) => <button type="button" key={value} disabled={busy} onClick={() => void action(value)}>{label}</button>)}
      </div>}
    </>}
  </section>
}
