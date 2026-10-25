import AppRouter from './router/AppRouter'
import { CheckInProvider } from './pages/checkin/CheckInProvider'

export default function App() {
  return <CheckInProvider><AppRouter /></CheckInProvider>
}
