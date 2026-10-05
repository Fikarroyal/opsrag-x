import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { InvestigationPicker } from '@/components/InvestigationPicker'
import { LogTable } from '@/components/LogTable'
import { Timeline } from '@/components/Timeline'
import { Card, DataState, DateRangeFilter, EmptyState, PageHeader, Pagination, SearchInput, Select } from '@/components/ui'
import { endpoints } from '@/services/endpoints'

export default function LogsPage() {
  const [f, setF] = useState({ q: '', hostname: '', service: '', level: '', event_type: '', source: '', start: '2026-09-28T09:35', end: '2026-09-28T09:50' })
  const [page, setPage] = useState(1)
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const inv = sp.get('investigation') ?? undefined
  const filters = useQuery({ queryKey: ['log-filters'], queryFn: endpoints.logFilters })
  const q = useQuery({ queryKey: ['logs', f, page], queryFn: () => endpoints.logs({ ...f, start: f.start ? `${f.start}:00` : undefined, end: f.end ? `${f.end}:00` : undefined, page, page_size: 50 }), placeholderData: (p) => p })
  const corr = useQuery({ queryKey: ['correlated', inv], queryFn: () => endpoints.correlated(inv as string), enabled: !!inv })
  const set = (k: keyof typeof f) => (v: string) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <>
      <PageHeader title="Log Explorer" subtitle="Pencarian log server & jaringan (terindeks, berpaginasi). Data sintetis 20-28 Sep 2026." actions={<InvestigationPicker value={inv} onChange={(v) => nav(v ? `/logs?investigation=${v}` : '/logs')} />} />
      <Card className="mb-4">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <SearchInput value={f.q} onChange={set('q')} placeholder="Cari pesan log" />
          <Select value={f.hostname} onChange={set('hostname')} options={filters.data?.hostnames.slice(0, 200) ?? []} placeholder="Semua hostname" />
          <Select value={f.service} onChange={set('service')} options={filters.data?.services ?? []} placeholder="Semua service" />
          <Select value={f.level} onChange={set('level')} options={['INFO', 'WARN', 'ERROR']} placeholder="Semua level" />
          <Select value={f.event_type} onChange={set('event_type')} options={filters.data?.event_types ?? []} placeholder="Semua event" />
          <Select value={f.source} onChange={set('source')} options={['server', 'network']} placeholder="Server & network" />
          <div className="sm:col-span-2"><DateRangeFilter start={f.start} end={f.end} onChange={(s, e) => { setF({ ...f, start: s, end: e }); setPage(1) }} /></div>
        </div>
      </Card>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="card xl:col-span-2"><DataState query={q}>{(d) => (<><LogTable rows={d.items} /><Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} /></>)}</DataState></div>
        <Card title="AI Correlated Events">
          {!inv ? <EmptyState title="Pilih investigasi" description="Event hasil korelasi temporal AI akan tampil di sini." /> : (
            <DataState query={corr} isEmpty={(d) => d.events.length === 0}>
              {(d) => (<>{d.patterns.map((p) => <div key={p.name} className="mb-2 rounded bg-slate-50 p-2 text-xs"><div className="font-mono">{p.name}</div>skor {p.correlation_score.toFixed(2)} - {p.order_ok ? 'urutan konsisten' : 'urutan tidak konsisten'}</div>)}<Timeline items={d.events.slice(0, 25)} /></>)}
            </DataState>
          )}
        </Card>
      </div>
    </>
  )
}
