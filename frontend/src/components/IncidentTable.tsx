import { Link } from 'react-router-dom'
import { SeverityBadge, StatusBadge, EmptyState } from '@/components/ui'
import { cap, fmtDateTime } from '@/lib/format'
import type { Incident } from '@/types/api'

export function IncidentTable({ items }: { items: Incident[] }) {
  if (items.length === 0) return <EmptyState title="Tidak ada incident" description="Ubah filter atau buat incident baru." />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50"><tr>{['Ticket', 'Judul', 'Unit', 'Layanan', 'Kategori', 'Severity', 'Status', 'Waktu kejadian'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((i) => (
            <tr key={i.id} className="hover:bg-slate-50">
              <td className="td font-mono text-xs"><Link className="text-brand-600 hover:underline" to={`/incidents/${i.id}`}>{i.ticket_number}</Link></td>
              <td className="td max-w-xs truncate" title={i.title}>{i.title}</td>
              <td className="td">{i.affected_unit ?? 'n/a'}</td>
              <td className="td">{i.affected_service ?? 'n/a'}</td>
              <td className="td">{cap(i.category)}</td>
              <td className="td"><SeverityBadge severity={i.severity} /></td>
              <td className="td"><StatusBadge status={i.status} /></td>
              <td className="td whitespace-nowrap font-mono text-xs">{fmtDateTime(i.occurred_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
