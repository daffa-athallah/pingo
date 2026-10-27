import { Link, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import BottomNav from './BottomNav'
import NotificationCenter from '../../features/notifications/NotificationCenter'
import JudgeGuide from '../../features/demo/JudgeGuide'
import SaveScreenshotButton from '../../features/demo/SaveScreenshotButton'
import NearbyAware from '../../features/nearby/NearbyAware'

export default function AppShell() {
  const { pathname, search } = useLocation()
  const visualPreview = pathname === '/context-simulator' && new URLSearchParams(search).get('mode') !== 'agents'
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    window.scrollTo(0, 0)
    mainRef.current?.focus({ preventScroll: true })
  }, [pathname])

  return (
    <div className={`app-shell${pathname === '/check-in' ? ' checkin-shell' : ''}${pathname === '/agent-activity' ? ' wide-shell' : ''}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <main className="app-main" id="main-content" ref={mainRef} tabIndex={-1}>
        <Outlet />
        {(import.meta.env.DEV || ['localhost', '127.0.0.1'].includes(window.location.hostname)) && pathname !== '/context-simulator' && <Link className="context-dev-link" to="/context-simulator">Developer: Context Simulator</Link>}
      </main>
      {!visualPreview && !(import.meta.env.DEV && pathname === '/dev/notifications') && <NotificationCenter />}
      <BottomNav />
      <JudgeGuide />
      <div className="floating-row">
        <NearbyAware />
        <SaveScreenshotButton />
      </div>
    </div>
  )
}
