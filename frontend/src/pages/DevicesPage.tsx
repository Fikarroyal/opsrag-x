import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Card, DataState, PageHeader, Pagination, SearchInput, Select, StatusBadge } from '@/components/ui'
import { cap, fmtDateTime } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function DevicesPage() {
  const [f, setF] = useState({ q: '', unit: '', device_type: '', status: '' })
  const [page, setPage] = useState(1)
  const filters = useQuery({ queryKey: ['device-filters'], queryFn: endpoints.deviceFilters })
  const q = useQuery({ queryKey: ['devices', f, page], queryFn: () => endpoints.devices({ ...f, page, page_size: 20 }), placeholderData: (p) => p })
  const set = (k: keyof typeof f) => (v: string) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <>
      <PageHeader title="Device Inventory" subtitle="Endpoint dan perangkat jaringan (sintetis)" />
      <Card className="mb-4"><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"><SearchInput value={f.q} onChange={set('q')} placeholder="Cari hostname / IP" /><Select value={f.unit} onChange={set('unit')} options={filters.data?.units ?? []} placeholder="Semua unit" /><Select value={f.device_type} onChange={set('device_type')} options={filters.data?.device_types ?? []} placeholder="Semua tipe" /><Select value={f.status} onChange={set('status')} options={['online', 'offline']} placeholder="Semua status" /></div></Card>
      <div className="card"><DataState query={q} isEmpty={(d) => d.items.length === 0}>{(d) => (<><div className="overflow-x-auto"><table className="min-w-full divide-y divide-slate-100"><thead className="bg-slate-50"><tr>{['Hostname', 'IP', 'MAC', 'Unit', 'VLAN', 'Tipe', 'OS', 'Switch / port', 'Status', 'Last seen'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
        {d.items.map((x) => (<tr key={x.id} className="hover:bg-slate-50"><td className="td font-mono text-xs font-semibold">{x.hostname}</td><td className="td font-mono text-xs">{x.ip_address}</td><td className="td font-mono text-xs">{x.mac_address}</td><td className="td">{x.unit}</td><td className="td">{x.vlan}</td><td className="td">{cap(x.device_type)}</td><td className="td">{x.operating_system}</td><td className="td font-mono text-xs">{x.switch ?? 'n/a'} {x.switch_port ? `/ ${x.switch_port}` : ''}</td><td className="td"><StatusBadge status={x.status} /></td><td className="td font-mono text-xs">{fmtDateTime(x.last_seen)}</td></tr>))}
      </tbody></table></div><Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} /></>)}</DataState></div>
    </>
  )
}
