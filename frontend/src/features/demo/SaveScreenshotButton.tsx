import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getHealth } from '../../services/runsApi'
import './save-button.css'

/** A way into the upload page from the product screens. Shown only where uploading is allowed: the resettable demo workspace, or a sample
 *  workspace with live models configured. The canonical (permanent Zetaris) backend never shows it. */
export default function SaveScreenshotButton() {
  const [allowed, setAllowed] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(health => setAllowed(health.mode === 'real' || health.mode === 'demo' || (health.mode === 'sample' && !!health.live_models))).catch(() => setAllowed(false))
    return () => controller.abort()
  }, [])
  if (!allowed || pathname === '/demo') return null
  return <Link className="save-screenshot-button" to="/demo" aria-label="Sync screenshots"><span aria-hidden="true">+</span> Sync screenshots</Link>
}
