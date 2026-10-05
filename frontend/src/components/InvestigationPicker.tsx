import { useQuery } from '@tanstack/react-query'
import { fmtDateTime } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export function InvestigationPicker({ value, onChange }: { value?: string; onChange: (id: string) => void }) {
  const q = useQuery({ queryKey: ['investigations', 'picker'], queryFn: async () => {
    const inv = await endpoints.investigations({ status: 'completed', page_size: 30 })
    const inc = await endpoints.incidents({ page_size: 100 })
    const names = new Map(inc.items.map((i) => [i.id, i.ticket_number]))
    return inv.items.map((i) => ({ ...i, ticket: names.get(i.incident_id) ?? i.incident_id.slice(0, 8) }))
  } })
  return (
    <select className="input min-w-[18rem]" value={value ?? ''} onChange={(e) => onChange(e.target.value)} aria-label="Pilih investigasi">
      <option value="">{q.isPending ? 'Memuat investigasi...' : q.data?.length ? 'Pilih investigasi' : 'Belum ada investigasi selesai'}</option>
      {q.data?.map((i) => <option key={i.id} value={i.id}>{i.ticket} · {fmtDateTime(i.started_at)} · {i.root_cause_category ?? 'inconclusive'}</option>)}
    </select>
  )
}
