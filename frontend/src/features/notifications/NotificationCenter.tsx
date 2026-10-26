import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { actOnNotification, getNotifications } from '../../services/api'
import type { PingoNotification } from '../../services/api'
import { showSystemNotification } from './systemNotifications'
import './notifications.css'

const pollMs = Math.max(3000, Number(import.meta.env.VITE_NOTIFICATION_POLL_MS) || 15000)

/** Poll persisted decisions only. An acknowledgement means rendered in this open tab, never OS push. */
export default function NotificationCenter() {
  const [notices, setNotices] = useState<PingoNotification[]>([])
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
          for (const notice of unread) void showSystemNotification(notice)
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
    for (const n of notices) if (n.payload.delivery_status === 'APPROVED') {
      void actOnNotification(n.notification_id, 'DELIVERED').then(updated => {
        setNotices(current => current.map(item => item.notification_id === updated.notification_id ? updated : item))
      }).catch(() => { /* Keep APPROVED until the server confirms delivery. */ })
    }
  }, [notices])
  if (!notices.length) return null
  return <aside className="pingo-notices" aria-label="New Pingo recalls" aria-live="polite">
    {notices.map(n => <Link className="pingo-notice" key={n.notification_id} to={`/recalls/${n.notification_id}`}>
      <span className="pingo-notice-source">{n.payload.sources.includes('SIMULATED') ? 'Simulated context' : 'New recall'}</span>
      <strong>{n.payload.title}</strong><span>Open recall</span>
    </Link>)}
  </aside>
}
