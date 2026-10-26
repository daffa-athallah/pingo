import { Link, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import BottomNav from './BottomNav'
import NotificationCenter from '../../features/notifications/NotificationCenter'
import JudgeGuide from '../../features/demo/JudgeGuide'
import SaveScreenshotButton from '../../features/demo/SaveScreenshotButton'
import NotificationSetup from '../../features/notifications/NotificationSetup'

export default function AppShell() {
  const { pathname } = useLocation()
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
        <NotificationSetup />
        {(import.meta.env.DEV || ['localhost', '127.0.0.1'].includes(window.location.hostname)) && pathname !== '/context-simulator' && <Link className="context-dev-link" to="/context-simulator">Developer: Context Simulator</Link>}
      </main>
      <NotificationCenter />
      <BottomNav />
      <JudgeGuide />
      <SaveScreenshotButton />
    </div>
  )
}
