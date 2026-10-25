import { NavLink, useLocation } from 'react-router-dom'

export default function BottomNav() {
  const { pathname } = useLocation()
  const inHome = pathname === '/' || pathname.startsWith('/category/') || pathname.startsWith('/entity/')

  return (
    <nav className="bottom-nav" aria-label="Main navigation">
      <NavLink to="/" end className={`bottom-nav-link${inHome ? ' is-active' : ''}`}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z" />
        </svg>
        Home
      </NavLink>
      <NavLink to="/check-in" className={({ isActive }) => `bottom-nav-link${isActive ? ' is-active' : ''}`}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="4" y="4" width="16" height="16" rx="5" />
          <path d="m8 12 3 3 5-6" />
        </svg>
        Check-in
      </NavLink>
    </nav>
  )
}
