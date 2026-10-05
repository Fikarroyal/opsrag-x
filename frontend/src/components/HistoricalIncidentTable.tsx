import { Badge, EmptyState, SeverityBadge } from '@/components/ui'
import { cap } from '@/lib/format'

export interface HistRow { incident_key: string; timestamp: string; unit: string | null; description: string; category: string; severity: string; root_cause: string; root_cause_category: string; resolution: string | null; resolution_time_minutes: number | null; similarity?: number | null }

export function HistoricalIncidentTable({ rows, showSimilarity }: { rows: HistRow[]; showSimilarity?: boolean }) {
  if (rows.length === 0) return <EmptyState title="Tidak ada incident historis" />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50"><tr>{['Incident', 'Tanggal', 'Unit', 'Kategori', 'Root cause', 'Resolusi', 'Waktu (mnt)', ...(showSimilarity ? ['Kemiripan'] : [])].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={r.incident_key} className="align-top hover:bg-slate-50">
              <td className="td"><div className="font-mono text-xs font-semibold">{r.incident_key}</div><div className="max-w-xs text-xs text-slate-500">{r.description}</div></td>
              <td className="td whitespace-nowrap font-mono text-xs">{r.timestamp.slice(0, 10)}</td>
              <td className="td">{r.unit ?? 'n/a'}</td>
              <td className="td"><div>{cap(r.category)}</div><SeverityBadge severity={r.severity} /></td>
              <td className="td max-w-xs"><Badge>{cap(r.root_cause_category)}</Badge><div className="mt-1 text-xs">{r.root_cause}</div></td>
              <td className="td max-w-xs text-xs">{r.resolution ?? 'n/a'}</td>
              <td className="td text-center">{r.resolution_time_minutes ?? 'n/a'}</td>
              {showSimilarity && <td className="td text-center font-semibold text-brand-700">{r.similarity !== null && r.similarity !== undefined ? `${(r.similarity * 100).toFixed(0)}%` : '-'}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
