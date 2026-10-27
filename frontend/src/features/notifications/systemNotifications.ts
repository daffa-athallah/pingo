import type { PingoNotification } from '../../services/api'

const shownKey = 'pingo.system-notifications.shown.v1'

export function notificationCopy(notice: PingoNotification) {
  const entityTitle = notice.payload.entities.length === 1 ? notice.payload.entities[0].name : ''
  const title = entityTitle || notice.payload.title.replace(/^Interested in\s+/i, '') || 'Saved intention'
  // Concise approved delivery copy belongs in the banner; the Critic's full reason stays in Why now?.
  const message = notice.payload.message.trim()
  const body = !message || message === 'An intention you saved may be relevant now. Revisit the evidence behind it.'
    ? 'Something you saved might fit this moment. Take another look?' : message
  const triggers = notice.payload.trigger_types.map(type => type.charAt(0) + type.slice(1).toLowerCase()).join(' + ')
  const mode = notice.payload.sources.includes('SIMULATED') ? 'Simulated' : 'Live'
  return { title, body, context: triggers ? `${mode} · ${triggers}` : `${mode} context` }
}

function shown(): Set<string> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(shownKey) ?? '[]')
    return new Set(Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [])
  } catch { return new Set() }
}

export function notificationSupport(): 'insecure' | 'unsupported' | NotificationPermission {
  if (!window.isSecureContext) return 'insecure'
  if (!('Notification' in window) || !('serviceWorker' in navigator)) return 'unsupported'
  return Notification.permission
}

export async function enableSystemNotifications(): Promise<NotificationPermission> {
  if (notificationSupport() === 'insecure' || notificationSupport() === 'unsupported') throw new Error('Notifications need the installed pingo app over HTTPS.')
  return Notification.requestPermission()
}

export async function showSystemNotification(notice: PingoNotification): Promise<boolean> {
  if (notice.payload.sources.includes('CACHED')) return false
  if (notificationSupport() !== 'granted') return false
  const history = shown()
  if (history.has(notice.notification_id)) return false
  const copy = notificationCopy(notice)
  const registration = await navigator.serviceWorker.ready
  await registration.showNotification(copy.title, {
    body: copy.body,
    icon: '/brand/production/pingo-icon-192.png',
    badge: '/brand/production/pingo-icon-192.png',
    tag: notice.notification_id,
    data: { url: `/recalls/${encodeURIComponent(notice.notification_id)}` },
  })
  history.add(notice.notification_id)
  localStorage.setItem(shownKey, JSON.stringify([...history].slice(-100)))
  return true
}
