import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Card, ConfirmDialog, DataState, KeyValue, PageHeader, SeverityBadge, StatusBadge } from '@/components/ui'
import { useToast } from '@/hooks/toast-context'
import { cap, fmtDateTime, pct } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function IncidentDetailPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [confirm, setConfirm] = useState(false)
  const [resolveOpen, setResolveOpen] = useState(false)
  const [resolution, setResolution] = useState('')
  const inc = useQuery({ queryKey: ['incident', id], queryFn: () => endpoints.incident(id) })
  const invs = useQuery({ queryKey: ['incident-investigations', id], queryFn: () => endpoints.incidentInvestigations(id) })
  const events = useQuery({ queryKey: ['incident-events', id], queryFn: () => endpoints.incidentEvents(id) })
  const start = useMutation({ mutationFn: () => endpoints.investigate(id), onSuccess: (r) => { toast.push('info', 'Investigasi dimulai'); void qc.invalidateQueries({ queryKey: ['incident', id] }); nav(`/investigations/${r.id}`) }, onError: (e: Error) => { setConfirm(false); toast.push('error', e.message) } })
  const resolve = useMutation({ mutationFn: () => endpoints.resolveIncident(id, { resolution }), onSuccess: () => { toast.push('success', 'Incident ditandai selesai'); setResolveOpen(false); void qc.invalidateQueries({ queryKey: ['incident', id] }); void qc.invalidateQueries({ queryKey: ['incident-events', id] }) }, onError: (e: Error) => toast.push('error', e.message) })
  return (
    <DataState query={inc}>
      {(i) => (
        <>
          <PageHeader title={`${i.ticket_number} · ${i.title}`} subtitle="Detail incident" actions={<>
            <button type="button" className="btn-secondary" disabled={i.status === 'resolved'} onClick={() => setResolveOpen(true)}>Tandai selesai</button>
            <button type="button" className="btn-primary" onClick={() => setConfirm(true)}><Play className="h-4 w-4" /> Start Investigation</button>
          </>} />
          <div className="space-y-4">
            <Card>
              <KeyValue items={[
                { k: 'Ticket', v: <span className="font-mono">{i.ticket_number}</span> }, { k: 'Status', v: <StatusBadge status={i.status} /> }, { k: 'Severity', v: <SeverityBadge severity={i.severity} /> }, { k: 'Category', v: cap(i.category) },
                { k: 'Affected unit', v: i.affected_unit ?? 'n/a' }, { k: 'Affected device', v: i.affected_device || 'n/a' }, { k: 'Affected service', v: i.affected_service ?? 'n/a' }, { k: 'Waktu kejadian', v: <span className="font-mono text-xs">{fmtDateTime(i.occurred_at)}</span> },
                { k: 'Dibuat', v: <span className="font-mono text-xs">{fmtDateTime(i.created_at)}</span> }, { k: 'Pelapor', v: i.reporter_name ?? 'n/a' },
              ]} />
            </Card>
            <Card title="Deskripsi"><p className="whitespace-pre-line text-sm text-slate-700">{i.description}</p></Card>
            <Card title="Investigasi AI">
              <DataState query={invs} isEmpty={(d) => d.length === 0} emptyTitle="Belum ada investigasi" emptyDescription="Klik Start Investigation untuk menjalankan alur investigasi multi-langkah.">
                {(list) => (
                  <table className="min-w-full"><thead><tr>{['Mulai', 'Status', 'Root cause', 'Confidence', 'Mode', 'Durasi', ''].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
                    {list.map((v) => (<tr key={v.id}><td className="td font-mono text-xs">{fmtDateTime(v.started_at)}{v.parent_investigation_id ? ' (replay)' : ''}</td><td className="td"><StatusBadge status={v.status} /></td><td className="td">{cap(v.root_cause_category ?? 'inconclusive')}</td><td className="td">{pct(v.confidence_score)}</td><td className="td">{v.ai_mode ?? 'n/a'}</td><td className="td">{v.duration_ms ? `${(v.duration_ms / 1000).toFixed(1)} dtk` : '-'}</td><td className="td"><Link className="text-brand-600" to={`/investigations/${v.id}`}>Buka</Link></td></tr>))}
                  </tbody></table>
                )}
              </DataState>
            </Card>
            <Card title="Audit events">
              <DataState query={events} isEmpty={(d) => d.length === 0}>
                {(list) => <ul className="max-h-72 space-y-1 overflow-auto text-xs">{list.map((e) => <li key={e.id} className="flex gap-2"><span className="font-mono text-slate-400">{fmtDateTime(e.timestamp)}</span><span className="font-semibold text-slate-600">{e.event_type}</span><span className="text-slate-600">{e.message}</span></li>)}</ul>}
              </DataState>
            </Card>
          </div>
          <ConfirmDialog open={confirm} title="Mulai investigasi AI?" busy={start.isPending} confirmLabel="Mulai" onConfirm={() => start.mutate()} onCancel={() => setConfirm(false)}
            message="Sistem menjalankan investigasi multi-langkah memakai tool diagnostik READ-ONLY dan tidak mengubah sistem apapun. Hasilnya berupa rekomendasi yang perlu diverifikasi IT Support." />
          <ConfirmDialog open={resolveOpen} title="Tandai incident selesai" busy={resolve.isPending} confirmLabel="Tandai selesai" onConfirm={() => resolution.trim().length >= 5 && resolve.mutate()} onCancel={() => setResolveOpen(false)}
            message={<div><p className="mb-2">Catat tindakan penyelesaian yang dilakukan IT Support (min. 5 karakter).</p><textarea className="input min-h-[80px]" value={resolution} onChange={(e) => setResolution(e.target.value)} aria-label="Resolusi" /></div>} />
        </>
      )}
    </DataState>
  )
}
