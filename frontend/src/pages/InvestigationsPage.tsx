import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Card, DataState, PageHeader, Pagination, Select, StatusBadge } from '@/components/ui'
import { cap, fmtDateTime, pct } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function InvestigationsPage() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const q = useQuery({ queryKey: ['investigations', page, status], queryFn: () => endpoints.investigations({ page, page_size: 12, status }), refetchInterval: 5000, placeholderData: (p) => p })
  const inc = useQuery({ queryKey: ['incident-names'], queryFn: () => endpoints.incidents({ page_size: 100 }) })
  const names = new Map(inc.data?.items.map((i) => [i.id, i]) ?? [])
  return (
    <>
      <PageHeader title="AI Investigation" subtitle="Seluruh investigasi. Mulai investigasi baru dari halaman detail incident." actions={<Link className="btn-secondary" to="/incidents">Pilih incident</Link>} />
      <Card className="mb-4"><div className="max-w-xs"><Select value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={['queued', 'running', 'completed', 'failed']} placeholder="Semua status" /></div></Card>
      <div className="card">
        <DataState query={q} isEmpty={(d) => d.items.length === 0} emptyTitle="Belum ada investigasi" emptyDescription="Buka sebuah incident lalu klik Start Investigation.">
          {(d) => (<>
            <table className="min-w-full"><thead className="bg-slate-50"><tr>{['Incident', 'Mulai', 'Status', 'Root cause', 'Confidence', 'Mode AI', 'Durasi', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
              {d.items.map((v) => (<tr key={v.id} className="hover:bg-slate-50"><td className="td font-mono text-xs">{names.get(v.incident_id)?.ticket_number ?? v.incident_id.slice(0, 8)}<div className="max-w-xs truncate font-sans text-slate-500">{names.get(v.incident_id)?.title}</div></td><td className="td font-mono text-xs">{fmtDateTime(v.started_at)}</td><td className="td"><StatusBadge status={v.status} /></td><td className="td">{cap(v.root_cause_category ?? (v.status === 'completed' ? 'inconclusive' : null))}</td><td className="td">{pct(v.confidence_score)}</td><td className="td">{v.ai_mode ?? 'n/a'}</td><td className="td">{v.duration_ms ? `${(v.duration_ms / 1000).toFixed(1)} dtk` : '-'}</td><td className="td"><Link className="text-brand-600" to={`/investigations/${v.id}`}>Buka</Link></td></tr>))}
            </tbody></table>
            <Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} />
          </>)}
        </DataState>
      </div>
    </>
  )
}
