import { Link } from 'react-router-dom'
import NotificationSetup from './NotificationSetup'

export default function NotificationSettings() {
  return <section className="page notification-settings"><Link className="back-link" to="/">Back to your collection</Link>
    <header className="page-header"><h1>Your pings</h1><p>Choose whether pingo can let you know when a saved thing fits the moment.</p></header>
    <NotificationSetup />
    {import.meta.env.DEV && <Link className="back-link" to="/dev/notifications">Try notification UI preview</Link>}
    <p>You can always browse your collection without notifications. When pingo has something relevant, it also appears in the open app.</p>
  </section>
}
