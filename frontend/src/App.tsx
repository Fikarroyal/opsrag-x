import { Route, Routes } from 'react-router-dom'
import { GuestOnly, RequireAuth } from '@/components/AuthProvider'
import { Layout } from '@/components/Layout'
import { EmptyState } from '@/components/ui'
import AiConfigPage from '@/pages/AiConfigPage'
import AnalyticsPage from '@/pages/AnalyticsPage'
import CreateIncidentPage from '@/pages/CreateIncidentPage'
import DashboardPage from '@/pages/DashboardPage'
import DevicesPage from '@/pages/DevicesPage'
import EvidencePage from '@/pages/EvidencePage'
import HistoricalPage from '@/pages/HistoricalPage'
import IncidentDetailPage from '@/pages/IncidentDetailPage'
import IncidentsPage from '@/pages/IncidentsPage'
import InvestigationPage from '@/pages/InvestigationPage'
import InvestigationsPage from '@/pages/InvestigationsPage'
import LoginPage from '@/pages/LoginPage'
import LogsPage from '@/pages/LogsPage'
import MapPage from '@/pages/MapPage'
import RegisterPage from '@/pages/RegisterPage'
import ServersPage from '@/pages/ServersPage'
import ServicesPage from '@/pages/ServicesPage'
import SopsPage from '@/pages/SopsPage'
import TimelinePage from '@/pages/TimelinePage'

export default function App() {
  return (
    <Routes>
      <Route element={<GuestOnly />}>
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
      </Route>
      <Route element={<RequireAuth />}>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="incidents" element={<IncidentsPage />} />
        <Route path="incidents/new" element={<CreateIncidentPage />} />
        <Route path="incidents/:id" element={<IncidentDetailPage />} />
        <Route path="investigations" element={<InvestigationsPage />} />
        <Route path="investigations/:id" element={<InvestigationPage />} />
        <Route path="timeline/:id?" element={<TimelinePage />} />
        <Route path="evidence/:id?" element={<EvidencePage />} />
        <Route path="map" element={<MapPage />} />
        <Route path="devices" element={<DevicesPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="logs" element={<LogsPage />} />
        <Route path="sops" element={<SopsPage />} />
        <Route path="historical" element={<HistoricalPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="ai-config" element={<AiConfigPage />} />
        <Route path="*" element={<EmptyState title="Halaman tidak ditemukan" />} />
      </Route>
      </Route>
    </Routes>
  )
}
