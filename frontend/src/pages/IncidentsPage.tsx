import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { IncidentFilters, type IncidentFilterState } from '@/components/IncidentFilters'
import { IncidentTable } from '@/components/IncidentTable'
import { Card, DataState, PageHeader, Pagination } from '@/components/ui'
import { endpoints } from '@/services/endpoints'

export default function IncidentsPage() {
  const [f, setF] = useState<IncidentFilterState>({ q: '', status: '', severity: '', category: '', unit: '' })
  const [page, setPage] = useState(1)
  const q = useQuery({ queryKey: ['incidents', f, page], queryFn: () => endpoints.incidents({ ...f, page, page_size: 10 }), placeholderData: (p) => p })
  return (
    <>
      <PageHeader title="Incident List" subtitle="Tiket gangguan infrastruktur TI" actions={<Link to="/incidents/new" className="btn-primary">Create incident</Link>} />
      <Card className="mb-4"><IncidentFilters value={f} onChange={(v) => { setF(v); setPage(1) }} /></Card>
      <div className="card">
        <DataState query={q}>{(d) => (<><IncidentTable items={d.items} /><Pagination page={d.page} pageSize={d.page_size} total={d.total} onPage={setPage} /></>)}</DataState>
      </div>
    </>
  )
}
