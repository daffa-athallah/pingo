import { useState } from 'react'
import { enableSystemNotifications, notificationSupport } from './systemNotifications'

export default function NotificationSetup() {
  const [support, setSupport] = useState(notificationSupport)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  if (support === 'granted') return <p role="status">Notifications are enabled on this device.</p>
  if (support === 'unsupported') return <p>System notifications aren’t available in this browser. Your pings still appear while the app is open.</p>

  async function enable() {
    setBusy(true); setMessage('')
    try {
      const permission = await enableSystemNotifications()
      setSupport(permission)
      if (permission === 'denied') setMessage('Permission was declined. You can enable pingo later in your device notification settings.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Notifications could not be enabled.')
    } finally { setBusy(false) }
  }

  return <section className="notification-optin" aria-labelledby="notification-optin-title">
    <div>
      <h2 id="notification-optin-title">A ping at the right moment</h2>
      <p>{support === 'insecure' ? 'Open pingo from its HTTPS tailnet address to enable phone notifications.' : support === 'denied' ? 'Notifications are blocked. Enable pingo in your device notification settings.' : 'Add pingo to your iPhone Home Screen, open it there, then turn on notifications.'}</p>
      {message && <p className="notification-optin-error" role="alert">{message}</p>}
    </div>
    <div className="notification-optin-actions">
      {support === 'default' && <button type="button" onClick={() => void enable()} disabled={busy}>{busy ? 'Requesting…' : 'Turn on notifications'}</button>}
    </div>
  </section>
}
