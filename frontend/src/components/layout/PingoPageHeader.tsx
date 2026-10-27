import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import PingoMark from '../brand/PingoMark'
import RecallIcon from '../../pages/home/RecallIcon'

/** The same production symbol and profile treatment as Home. */
export default function PingoPageHeader({ action }: { action?: ReactNode }) {
  return <header className="pingo-page-header home-header">
    <Link className="pingo-page-home" to="/" aria-label="pingo home"><PingoMark className="home-pingo-mark" /></Link>
    <div className="pingo-page-actions">
      {action}
      <Link className="home-profile" to="/settings/notifications" aria-label="Profile and notification settings"><RecallIcon name="profile" /></Link>
    </div>
  </header>
}
