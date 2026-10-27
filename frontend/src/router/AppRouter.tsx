import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import HomePage from '../pages/home/HomePage'
import CheckInPage from '../pages/checkin/CheckInPage'
import CategoryPage from '../pages/category/CategoryPage'
import EntityDetailPage from '../pages/entity/EntityDetailPage'
import AgentActivity from '../features/agent-activity/AgentActivity'
import LiveAgentActivity from '../features/agent-activity/LiveAgentActivity'
import DemoUpload from '../features/demo/DemoUpload'
import ContextSimulator from '../pages/context/ContextSimulator'
import NotificationDetail from '../features/notifications/NotificationDetail'
import NotificationSettings from '../features/notifications/NotificationSettings'
import NotificationPreview from '../features/notifications/NotificationPreview'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="check-in" element={<CheckInPage />} />
          <Route path="settings/notifications" element={<NotificationSettings />} />
          {import.meta.env.DEV && <Route path="dev/notifications" element={<NotificationPreview />} />}
          <Route path="context-simulator" element={<ContextSimulator />} />
          <Route path="recalls/:notificationId" element={<NotificationDetail />} />
          <Route path="category/:category" element={<CategoryPage />} />
          <Route path="entity/:entityId" element={<EntityDetailPage />} />
          <Route path="agent-activity" element={import.meta.env.VITE_USE_MOCK === 'true' ? <AgentActivity /> : <LiveAgentActivity />} />
          <Route path="sync" element={<DemoUpload />} />
          <Route path="demo" element={<Navigate to="/sync" replace />} />  {/* the old address keeps working */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
