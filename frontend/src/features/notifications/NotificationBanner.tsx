import { Link } from 'react-router-dom'

interface Props {
  title: string
  body: string
  context: string
  createdAt?: string
  href?: string
  onOpen?: () => void
  onDismiss?: () => void
  dismissBusy?: boolean
  surface?: 'in-app' | 'iphone'
}

function relativeTime(value?: string) {
  const date = Date.parse(value ?? '')
  if (!Number.isFinite(date)) return 'now'
  const minutes = Math.max(0, Math.floor((Date.now() - date) / 60000))
  if (minutes < 1) return 'now'
  if (minutes < 60) return `${minutes}m ago`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
  return `${Math.floor(minutes / 1440)}d ago`
}

/** Custom web banner. The iphone variant is a simulation, never an OS notification. */
export default function NotificationBanner({ title, body, context, createdAt, href, onOpen, onDismiss, dismissBusy, surface = 'in-app' }: Props) {
  const content = <>
    <img className="pingo-notice-icon" src="/brand/production/pingo-icon-192.png" width="36" height="36" alt="" />
    <span className="pingo-notice-content">
      <span className="pingo-notice-heading"><span>Pingo</span><span className="pingo-notice-time">{relativeTime(createdAt)}</span></span>
      <strong>{title}</strong>
      <span className="pingo-notice-reason">{body}</span>
      <span className="pingo-notice-source">{context}</span>
    </span>
  </>
  return <div className={`pingo-notice-wrap pingo-notice-wrap--${surface}`}>
    {href ? <Link className="pingo-notice" to={href} aria-label={`Open ping: ${title}`} onClick={event => {
      if (onOpen) { event.preventDefault(); onOpen() }
    }}>{content}</Link> : <button type="button" className="pingo-notice" onClick={onOpen} aria-label={`Open preview: ${title}`}>{content}</button>}
    {onDismiss && <button type="button" className="pingo-notice-dismiss" onClick={onDismiss} disabled={dismissBusy} aria-label="Dismiss notification">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true"><path d="m4 4 8 8m0-8-8 8" /></svg>
    </button>}
  </div>
}
