import { useQuery } from '@tanstack/react-query'
import { Activity, AlertOctagon, CheckCircle2, Clock, Siren, Workflow } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { ReactNode } from 'react'
import { Card, DataState, PageHeader, SeverityBadge, StatCard, StatusBadge } from '@/components/ui'
import { CHART_COLORS, SEVERITY_COLOR, cap, fmtDateTime } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

const H = 150 // chart height (px): compact so the whole overview fits one screen
const AXIS = { fontSize: 10, fill: '#64748b' }
const GRID = '#e2e8f0'
const legendFmt = (v: string) => <span className="text-[11px] text-slate-600">{cap(v)}</span>

function topWithRest(rows: { name: string; value: number }[], keep = 5): { name: string; value: number }[] {
  const sorted = [...rows].sort((a, b) => b.value - a.value)
  const rest = sorted.slice(keep).reduce((n, r) => n + r.value, 0)
  return rest > 0 ? [...sorted.slice(0, keep), { name: 'lainnya', value: rest }] : sorted
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return <Card title={title} dense>{children}</Card>
}

export default function DashboardPage() {
  const q = useQuery({ queryKey: ['dashboard'], queryFn: endpoints.dashboard, refetchInterval: 15000 })
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: endpoints.scenarios })
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Ringkasan operasional insiden infrastruktur TI RS Yogyakarta" actions={<Link to="/incidents/new" className="btn-primary">Buat incident</Link>} />
      <DataState query={q} skeletonRows={8}>
        {(s) => {
          const rootCauses = topWithRest(s.root_cause_distribution)
          return (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              <StatCard label="Total incident" value={s.total_incidents} icon={<Siren className="h-4 w-4" />} tone="blue" hint={`+${s.historical_incidents} historis`} />
              <StatCard label="Incident terbuka" value={s.open_incidents} icon={<Activity className="h-4 w-4" />} tone="amber" />
              <StatCard label="Incident kritis" value={s.critical_incidents} icon={<AlertOctagon className="h-4 w-4" />} tone="red" />
              <StatCard label="Investigasi aktif" value={s.investigations_running} icon={<Workflow className="h-4 w-4" />} tone="blue" />
              <StatCard label="Incident selesai" value={s.resolved_incidents} icon={<CheckCircle2 className="h-4 w-4" />} tone="green" />
              <StatCard label="Rata-rata resolusi" value={s.average_resolution_minutes ? `${s.average_resolution_minutes.toFixed(0)} mnt` : 'n/a'} icon={<Clock className="h-4 w-4" />} hint="historis dan selesai" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              <ChartCard title="Incident per kategori">
                <ResponsiveContainer width="100%" height={H}>
                  <BarChart data={[...s.incident_by_category].sort((a, b) => b.value - a.value).slice(0, 6)} layout="vertical" margin={{ left: 0, right: 12, top: 0, bottom: 0 }} barSize={9}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis dataKey="name" type="category" width={78} tick={AXIS} axisLine={false} tickLine={false} tickFormatter={cap} />
                    <Tooltip cursor={{ fill: '#f1f5f9' }} />
                    <Bar dataKey="value" name="Incident" fill="#2563eb" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Incident per severity">
                <ResponsiveContainer width="100%" height={H}>
                  <PieChart>
                    <Pie data={s.incident_by_severity} dataKey="value" nameKey="name" innerRadius="52%" outerRadius="82%" paddingAngle={2} cx="38%" stroke="none" isAnimationActive={false}>
                      {s.incident_by_severity.map((d) => <Cell key={d.name} fill={SEVERITY_COLOR[d.name] ?? '#94a3b8'} />)}
                    </Pie>
                    <Tooltip />
                    <Legend layout="vertical" align="right" verticalAlign="middle" iconSize={8} formatter={legendFmt} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Distribusi root cause">
                <ResponsiveContainer width="100%" height={H}>
                  <PieChart>
                    <Pie data={rootCauses} dataKey="value" nameKey="name" outerRadius="82%" cx="38%" stroke="#fff" strokeWidth={1} isAnimationActive={false}>
                      {rootCauses.map((d, i) => <Cell key={d.name} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                    <Legend layout="vertical" align="right" verticalAlign="middle" iconSize={8} formatter={legendFmt} />
                  </PieChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Tren incident per bulan">
                <ResponsiveContainer width="100%" height={H}>
                  <LineChart data={s.incident_trend} margin={{ left: -18, right: 8, top: 6, bottom: 0 }}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                    <XAxis dataKey="period" tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip />
                    <Line type="monotone" dataKey="incidents" name="Incident" stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Tren waktu resolusi (menit)">
                <ResponsiveContainer width="100%" height={H}>
                  <LineChart data={s.resolution_time_trend} margin={{ left: -18, right: 8, top: 6, bottom: 0 }}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
                    <XAxis dataKey="period" tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip />
                    <Line type="monotone" dataKey="avg_minutes" name="Rata-rata menit" stroke="#7c3aed" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </ChartCard>
              <ChartCard title="Ketersediaan layanan (%)">
                <ResponsiveContainer width="100%" height={H}>
                  <BarChart data={s.service_availability} layout="vertical" margin={{ left: 0, right: 12, top: 0, bottom: 0 }} barSize={9}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[80, 100]} ticks={[80, 90, 100]} tick={AXIS} axisLine={false} tickLine={false} />
                    <YAxis dataKey="service" type="category" width={92} tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip cursor={{ fill: '#f1f5f9' }} />
                    <Bar dataKey="availability" name="Ketersediaan" fill="#16a34a" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
              <Card title="Recent incidents" className="lg:col-span-2" actions={<Link to="/incidents" className="text-xs text-brand-600">Lihat semua</Link>}>
                <ul className="divide-y divide-slate-100">
                  {s.recent_incidents.map((i) => (
                    <li key={i.id} className="flex flex-wrap items-center gap-2 py-2">
                      <Link to={`/incidents/${i.id}`} className="font-mono text-xs text-brand-600 hover:underline">{i.ticket_number}</Link>
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-700">{i.title}</span>
                      <SeverityBadge severity={i.severity} /><StatusBadge status={i.status} />
                      <span className="font-mono text-xs text-slate-400">{fmtDateTime(i.occurred_at)}</span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card title="Skenario insiden">
                <DataState query={scenarios} isEmpty={(d) => d.length === 0}>
                  {(list) => (
                    <ul className="space-y-2">
                      {list.map((d) => (
                        <li key={d.id} className="rounded-md border border-slate-200 p-2.5">
                          <div className="text-sm font-medium text-slate-800">{d.id}. {d.name}</div>
                          <div className="text-xs text-slate-500">{d.description}</div>
                          {d.incident_id && <Link className="mt-1 inline-block text-xs text-brand-600" to={`/incidents/${d.incident_id}`}>Buka {d.ticket_number}</Link>}
                        </li>
                      ))}
                    </ul>
                  )}
                </DataState>
              </Card>
            </div>
            <p className="text-xs text-slate-400">Kategori: {s.incident_by_category.map((c) => `${cap(c.name)} ${c.value}`).join(' · ')}</p>
          </div>
          )
        }}
      </DataState>
    </>
  )
}
