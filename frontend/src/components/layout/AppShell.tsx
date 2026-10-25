import { Outlet, useLocation } from 'react-router-dom'
import { useEffect, useRef } from 'react'
import BottomNav from './BottomNav'

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
      </main>
      <BottomNav />
    </div>
  )
}
