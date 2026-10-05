import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { EvidenceCard } from '@/components/EvidenceCard'
import { InvestigationPicker } from '@/components/InvestigationPicker'
import { Card, DataState, EmptyState, PageHeader, Select } from '@/components/ui'
import { endpoints } from '@/services/endpoints'

export default function EvidencePage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [role, setRole] = useState('')
  const [source, setSource] = useState('')
  const q = useQuery({ queryKey: ['evidence', id, role, source], queryFn: () => endpoints.evidence(id as string, { role, source_type: source }), enabled: !!id })
  return (
    <>
      <PageHeader title="Evidence Explorer" subtitle="Evidence yang digunakan investigasi: sumber, prioritas, skor relevansi/temporal, dan perannya terhadap hipotesis utama" actions={<InvestigationPicker value={id} onChange={(v) => nav(v ? `/evidence/${v}` : '/evidence')} />} />
      {!id ? <EmptyState title="Pilih investigasi" /> : (
        <>
          <Card className="mb-4"><div className="grid max-w-xl gap-2 sm:grid-cols-2"><Select value={role} onChange={setRole} options={['supporting', 'contradicting', 'context']} placeholder="Semua peran" /><Select value={source} onChange={setSource} options={['mcp_tool', 'network_log', 'server_log', 'log_correlation', 'topology', 'device_inventory', 'historical_recent', 'historical_old', 'sop', 'incident_report']} placeholder="Semua sumber" /></div></Card>
          <DataState query={q} isEmpty={(d) => d.length === 0} emptyTitle="Tidak ada evidence pada filter ini">
            {(items) => <div className="grid gap-3 xl:grid-cols-2">{items.map((e) => <EvidenceCard key={e.id} e={{ key: e.evidence_key, source_type: e.source_type, source_id: e.source_id, timestamp: e.evidence_timestamp, content: e.evidence_text, kind: e.kind, relevance_score: e.relevance_score, temporal_score: e.temporal_score, temporal_relation: e.temporal_relation, role: e.role, confidence_contribution: e.confidence_contribution, priority_rank: e.priority_rank, reliability: 0.5 + 0.5 * (1 - (e.priority_rank - 1) / 8), tags: e.tags, hypothesis_roles: e.hypothesis_ids }} />)}</div>}
          </DataState>
        </>
      )}
    </>
  )
}
