import { useState } from 'react'
import { enableSystemNotifications, notificationSupport } from './systemNotifications'

export default function NotificationSetup() {
  const [support, setSupport] = useState(notificationSupport)
  const [busy, setBusy] = useState(false)
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem('pingo.notification-optin.dismissed') === 'true')
  const [message, setMessage] = useState('')
  if (dismissed || support === 'granted' || support === 'unsupported') return null

  async function enable() {
    setBusy(true); setMessage('')
    try {
      const permission = await enableSystemNotifications()
      setSupport(permission)
      if (permission === 'denied') setMessage('Permission was declined. You can enable Pingo later in your device notification settings.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Notifications could not be enabled.')
    } finally { setBusy(false) }
  }

  function dismiss() {
    sessionStorage.setItem('pingo.notification-optin.dismissed', 'true')
    setDismissed(true)
  }

  return <section className="notification-optin" aria-labelledby="notification-optin-title">
    <div>
      <h2 id="notification-optin-title">Get timely recalls</h2>
      <p>{support === 'insecure' ? 'Open Pingo from its HTTPS tailnet address to enable phone notifications.' : support === 'denied' ? 'Notifications are blocked. Enable Pingo in your device notification settings.' : 'Add Pingo to your iPhone Home Screen, open it there, then turn on notifications.'}</p>
      {message && <p className="notification-optin-error" role="alert">{message}</p>}
    </div>
    <div className="notification-optin-actions">
      {support === 'default' && <button type="button" onClick={() => void enable()} disabled={busy}>{busy ? 'Requesting…' : 'Turn on notifications'}</button>}
      <button className="notification-optin-later" type="button" onClick={dismiss}>Later</button>
    </div>
  </section>
}
