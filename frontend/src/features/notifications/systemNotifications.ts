import type { PingoNotification } from '../../services/api'

const shownKey = 'pingo.system-notifications.shown.v1'

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
  if (notificationSupport() === 'insecure' || notificationSupport() === 'unsupported') throw new Error('Notifications need the installed Pingo app over HTTPS.')
  return Notification.requestPermission()
}

export async function showSystemNotification(notice: PingoNotification): Promise<boolean> {
  if (notificationSupport() !== 'granted') return false
  const history = shown()
  if (history.has(notice.notification_id)) return false
  const registration = await navigator.serviceWorker.ready
  await registration.showNotification(notice.payload.title, {
    body: notice.payload.message,
    icon: '/pwa/icon-192.png',
    badge: '/pwa/icon-192.png',
    tag: notice.notification_id,
    data: { url: `/recalls/${encodeURIComponent(notice.notification_id)}` },
  })
  history.add(notice.notification_id)
  localStorage.setItem(shownKey, JSON.stringify([...history].slice(-100)))
  return true
}
