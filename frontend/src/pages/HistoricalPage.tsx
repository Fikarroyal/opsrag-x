import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { HistoricalIncidentTable } from '@/components/HistoricalIncidentTable'
import { InvestigationPicker } from '@/components/InvestigationPicker'
import { Card, DataState, PageHeader, Pagination, SearchInput, Select } from '@/components/ui'
import { CATEGORIES, UNITS } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function HistoricalPage() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const inv = sp.get('investigation') ?? undefined
  const [f, setF] = useState({ q: '', category: '', unit: '', root_cause_category: '' })
  const [page, setPage] = useState(1)
  const q = useQuery({ queryKey: ['historical', f, page, inv], queryFn: () => endpoints.historical({ ...f, investigation_id: inv, page, page_size: 10 }), placeholderData: (p) => p })
  const set = (k: keyof typeof f) => (v: string) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <>
      <PageHeader title="Historical Incidents" subtitle="Incident historis (sintetis). Dipilih investigasi: hanya incident yang dipakai sebagai supporting evidence beserta kemiripannya." actions={<InvestigationPicker value={inv} onChange={(v) => nav(v ? `/historical?investigation=${v}` : '/historical')} />} />
      <Card className="mb-4"><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4"><SearchInput value={f.q} onChange={set('q')} placeholder="Cari deskripsi / root cause" /><Select value={f.category} onChange={set('category')} options={CATEGORIES} placeholder="Semua kategori gejala" /><Select value={f.root_cause_category} onChange={set('root_cause_category')} options={CATEGORIES} placeholder="Semua root cause" /><Select value={f.unit} onChange={set('unit')} options={UNITS} placeholder="Semua unit" /></div></Card>
      <div className="card"><DataState query={q} isEmpty={(d) => d.items.length === 0}>{(d) => (<><HistoricalIncidentTable rows={d.items} showSimilarity={!!inv} /><Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} /></>)}</DataState></div>
    </>
  )
}
