import { useQuery } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { InvestigationPicker } from '@/components/InvestigationPicker'
import { Timeline } from '@/components/Timeline'
import { Badge, Card, DataState, EmptyState, PageHeader, StatusBadge } from '@/components/ui'
import { fmtDateTime } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function TimelinePage() {
  const { id } = useParams()
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['timeline', id], queryFn: () => endpoints.timeline(id as string), enabled: !!id })
  return (
    <>
      <PageHeader title="Investigation Timeline" subtitle="Audit trail setiap tahap investigasi dan urutan temporal event infrastruktur" actions={<InvestigationPicker value={id} onChange={(v) => nav(v ? `/timeline/${v}` : '/timeline')} />} />
      {!id ? <EmptyState title="Pilih investigasi" description="Pilih investigasi selesai pada daftar di kanan atas." /> : (
        <DataState query={q} skeletonRows={8}>
          {(d) => (
            <div className="grid gap-4 xl:grid-cols-2">
              <Card title={`Audit events (${d.events.length})`}>
                <ol className="space-y-2">
                  {d.events.map((e) => (
                    <li key={e.id} className="rounded-md border border-slate-200 p-2.5">
                      <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs text-slate-500">{fmtDateTime(e.timestamp)}</span><Badge>{e.event_type}</Badge><StatusBadge status={e.status} />{e.duration_ms !== null && <span className="ml-auto text-xs text-slate-400">{e.duration_ms.toFixed(1)} ms</span>}</div>
                      <p className="mt-1 text-sm text-slate-700">{e.message}</p>
                    </li>
                  ))}
                </ol>
              </Card>
              <Card title="Evidence timeline (temporal)">{d.evidence_timeline.length ? <Timeline items={d.evidence_timeline} /> : <EmptyState title="Tidak ada event temporal" />}</Card>
            </div>
          )}
        </DataState>
      )}
    </>
  )
}
