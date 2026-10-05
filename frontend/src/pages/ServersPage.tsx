import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, DataState, Meter, PageHeader, StatusBadge } from '@/components/ui'
import { SCENARIO_TIMES } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function ServersPage() {
  const [asOf, setAsOf] = useState('2026-09-28T09:47')
  const [host, setHost] = useState('SIMRS-APP-01')
  const q = useQuery({ queryKey: ['servers', asOf], queryFn: () => endpoints.servers({ as_of: asOf ? `${asOf}:00` : undefined }) })
  const end = new Date(`${asOf || '2026-09-28T09:47'}:00Z`)
  const start = new Date(end.getTime() - 40 * 60000)
  const iso = (d: Date) => d.toISOString().slice(0, 19)
  const m = useQuery({ queryKey: ['server-metrics', host, asOf], queryFn: () => endpoints.serverMetrics(host, { start: iso(start), end: iso(new Date(end.getTime() + 25 * 60000)) }) })
  return (
    <>
      <PageHeader title="Server Monitoring" subtitle="Status, CPU, memori dan layanan per server pada waktu yang dipilih (data sintetis 20-28 Sep 2026)" actions={<select className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} aria-label="Waktu pengamatan">{SCENARIO_TIMES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}</select>} />
      <DataState query={q} skeletonRows={6}>
        {(servers) => (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {servers.map((s) => (
                <button type="button" key={s.hostname} onClick={() => setHost(s.hostname)} className={`card p-4 text-left ${host === s.hostname ? 'ring-2 ring-brand-500' : ''}`}>
                  <div className="flex items-center justify-between"><div><div className="font-mono text-sm font-bold text-slate-900">{s.hostname}</div><div className="text-xs text-slate-500">{s.role} - {s.ip_address}</div></div><StatusBadge status={s.status} /></div>
                  <div className="mt-3 space-y-1.5 text-xs text-slate-500"><div>CPU <Meter value={(s.cpu ?? 0) / 100} tone={(s.cpu ?? 0) >= 85 ? 'bg-red-500' : 'bg-brand-500'} /></div><div>Memori <Meter value={(s.memory ?? 0) / 100} tone={(s.memory ?? 0) >= 90 ? 'bg-red-500' : 'bg-cyan-500'} /></div></div>
                  <div className="mt-2 flex flex-wrap gap-1">{s.services.map((v) => <span key={v.service} className="flex items-center gap-1 text-[11px] text-slate-600">{v.service} <StatusBadge status={v.status} /></span>)}</div>
                  <div className="mt-1 text-[11px] text-slate-400">Error 15 menit terakhir: {s.recent_errors}</div>
                </button>
              ))}
            </div>
            <Card title={`Tren CPU / memori · ${host}`}>
              <DataState query={m} isEmpty={(d) => d.length === 0} emptyTitle="Tidak ada sampel resource pada rentang ini">
                {(d) => <ResponsiveContainer width="100%" height={260}><LineChart data={d.map((x) => ({ ...x, time: x.timestamp.slice(11, 16) }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="time" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} unit="%" /><Tooltip /><Legend /><Line type="monotone" dataKey="cpu" stroke="#2563eb" dot={false} strokeWidth={2} name="CPU %" /><Line type="monotone" dataKey="memory" stroke="#7c3aed" dot={false} strokeWidth={2} name="Memori %" /></LineChart></ResponsiveContainer>}
              </DataState>
            </Card>
          </div>
        )}
      </DataState>
    </>
  )
}
