import { useEffect, useRef, useState } from 'react'
import { actOnNotification, getNotifications } from '../../services/api'
import type { PingoNotification } from '../../services/api'
import { notificationCopy, showSystemNotification } from './systemNotifications'
import NotificationBanner from './NotificationBanner'
import './notifications.css'

const pollMs = Math.max(3000, Number(import.meta.env.VITE_NOTIFICATION_POLL_MS) || 15000)

export function NoticeCard({ notice, onPreviewOpen, onDismiss, dismissBusy }: { notice: PingoNotification; onPreviewOpen?: () => void; onDismiss?: () => void; dismissBusy?: boolean }) {
  const copy = notificationCopy(notice)
  return <NotificationBanner href={`/recalls/${encodeURIComponent(notice.notification_id)}`} title={copy.title} body={copy.body}
    context={`${onPreviewOpen ? 'UI preview · ' : ''}${copy.context}`} createdAt={notice.created_at} onOpen={onPreviewOpen} onDismiss={onDismiss} dismissBusy={dismissBusy} />
}

/** Poll persisted decisions only. An acknowledgement means rendered in this open tab, never OS push. */
export default function NotificationCenter() {
  const [notices, setNotices] = useState<PingoNotification[]>([])
  const [dismissError, setDismissError] = useState('')
  const [dismissing, setDismissing] = useState<string[]>([])
  const dismissingIds = useRef(new Set<string>())
  const acknowledgingIds = useRef(new Set<string>())
  async function dismiss(id: string) {
    if (dismissingIds.current.has(id)) return
    dismissingIds.current.add(id)
    setDismissing(current => [...current, id]); setDismissError('')
    try {
      await actOnNotification(id, 'DISMISS')
      setNotices(current => current.filter(notice => notice.notification_id !== id))
      window.dispatchEvent(new Event('pingo-notifications-changed'))
    } catch { setDismissError('Couldn’t dismiss this ping. Try again.') }
    finally { dismissingIds.current.delete(id); setDismissing(current => current.filter(value => value !== id)) }
  }
  useEffect(() => {
    const controller = new AbortController()
    let busy = false
    async function refresh() {
      if (document.hidden || busy) return
      busy = true
      try {
        const values = await getNotifications(controller.signal)
        if (!controller.signal.aborted) {
          const unread = values.filter(n => !n.payload.read).slice(0, 3)
          setNotices(unread)
          for (const notice of unread) void showSystemNotification(notice).catch(() => { /* In-app delivery remains available if the OS refuses. */ })
        }
      } catch { /* Unavailable delivery never becomes a fake notice. */ }
      finally { busy = false }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), pollMs)
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('pingo-notifications-changed', refresh)
    return () => { controller.abort(); clearInterval(timer); document.removeEventListener('visibilitychange', refresh); window.removeEventListener('pingo-notifications-changed', refresh) }
  }, [])
  useEffect(() => {
    if (document.hidden) return
    for (const n of notices) if (n.payload.delivery_status === 'APPROVED' && !acknowledgingIds.current.has(n.notification_id)) {
      acknowledgingIds.current.add(n.notification_id)
      void actOnNotification(n.notification_id, 'DELIVERED').then(updated => {
        setNotices(current => current.map(item => item.notification_id === updated.notification_id ? updated : item))
      }).catch(() => { /* Keep APPROVED until the server confirms delivery. */ }).finally(() => acknowledgingIds.current.delete(n.notification_id))
    }
  }, [notices])
  if (!notices.length) return null
  return <aside className="pingo-notices" aria-label="New pingo notifications" aria-live="polite">
    {notices.map(notice => <NoticeCard key={notice.notification_id} notice={notice} dismissBusy={dismissing.includes(notice.notification_id)} onDismiss={() => void dismiss(notice.notification_id)} />)}
    {dismissError && <p className="pingo-dismiss-error" role="alert">{dismissError}</p>}
  </aside>
}
