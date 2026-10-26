import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from '../components/layout/AppShell'
import HomePage from '../pages/home/HomePage'
import CheckInPage from '../pages/checkin/CheckInPage'
import CategoryPage from '../pages/category/CategoryPage'
import EntityDetailPage from '../pages/entity/EntityDetailPage'
import AgentActivity from '../features/agent-activity/AgentActivity'
import LiveAgentActivity from '../features/agent-activity/LiveAgentActivity'

export default function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<HomePage />} />
          <Route path="check-in" element={<CheckInPage />} />
          <Route path="category/:category" element={<CategoryPage />} />
          <Route path="entity/:entityId" element={<EntityDetailPage />} />
          <Route path="agent-activity" element={import.meta.env.VITE_USE_MOCK === 'true' ? <AgentActivity /> : <LiveAgentActivity />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
