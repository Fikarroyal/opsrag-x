import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, DataState, Meter, PageHeader, StatusBadge } from '@/components/ui'
import { SCENARIO_TIMES, fmtDateTime } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function ServicesPage() {
  const [asOf, setAsOf] = useState('2026-09-27T13:20')
  const [svc, setSvc] = useState('DNS')
  const q = useQuery({ queryKey: ['services', asOf], queryFn: () => endpoints.services({ as_of: `${asOf}:00` }) })
  const hist = useQuery({ queryKey: ['service-history', svc, asOf], queryFn: () => endpoints.serviceHistory(svc, { start: `${new Date(new Date(`${asOf}:00Z`).getTime() - 30 * 60000).toISOString().slice(0, 19)}`, end: `${new Date(new Date(`${asOf}:00Z`).getTime() + 30 * 60000).toISOString().slice(0, 19)}` }) })
  return (
    <>
      <PageHeader title="Service Monitoring" subtitle="Status layanan IT dan availability (dari snapshot monitoring sintetis)" actions={<select className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} aria-label="Waktu pengamatan">{SCENARIO_TIMES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>} />
      <DataState query={q}>
        {(list) => (
          <div className="space-y-4">
            <div className="card overflow-x-auto"><table className="min-w-full divide-y divide-slate-100"><thead className="bg-slate-50"><tr>{['Layanan', 'Server', 'Port', 'Status', 'Response (ms)', 'HTTP', 'Availability', 'Dicek', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
              {list.map((s) => (<tr key={s.service} className="hover:bg-slate-50"><td className="td font-semibold">{s.service}</td><td className="td font-mono text-xs">{s.server}</td><td className="td">{s.port}</td><td className="td"><StatusBadge status={s.status === 'running' ? 'healthy' : s.status} /></td><td className="td">{s.response_time_ms}</td><td className="td">{s.http_status || 'n/a'}</td><td className="td w-40">{s.availability !== null ? <Meter value={s.availability / 100} tone="bg-green-500" /> : '-'}</td><td className="td font-mono text-xs">{fmtDateTime(s.last_checked)}</td><td className="td"><button type="button" className="text-brand-600" onClick={() => setSvc(s.service)}>Riwayat</button></td></tr>))}
            </tbody></table></div>
            <Card title={`Riwayat respons ${svc} (+-30 menit)`}>
              <DataState query={hist} isEmpty={(d) => d.length === 0} emptyTitle="Tidak ada riwayat">
                {(d) => <ResponsiveContainer width="100%" height={240}><BarChart data={d.map((x) => ({ time: x.timestamp.slice(11, 16), ms: x.response_time_ms, status: x.status }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="time" tick={{ fontSize: 10 }} /><YAxis /><Tooltip /><Bar dataKey="ms" name="Response (ms)">{d.map((x, i) => <Cell key={i} fill={x.status === 'running' ? '#16a34a' : x.status === 'degraded' ? '#f59e0b' : '#dc2626'} />)}</Bar></BarChart></ResponsiveContainer>}
              </DataState>
            </Card>
          </div>
        )}
      </DataState>
    </>
  )
}
