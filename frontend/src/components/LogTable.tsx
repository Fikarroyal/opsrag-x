import { EmptyState } from '@/components/ui'
import { cx } from '@/lib/cx'
import { fmtDateTime } from '@/lib/format'
import type { LogRow } from '@/types/api'

const LEVEL: Record<string, string> = { ERROR: 'text-red-600', CRITICAL: 'text-red-700', WARN: 'text-amber-600', INFO: 'text-slate-500' }

export function LogTable({ rows }: { rows: LogRow[] }) {
  if (rows.length === 0) return <EmptyState title="Tidak ada log" description="Tidak ada log yang cocok dengan filter pada rentang waktu ini." />
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50"><tr>{['Timestamp', 'Hostname', 'Service', 'Level', 'Event', 'Message'].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-slate-100 font-mono text-xs">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-slate-50">
              <td className="td whitespace-nowrap">{fmtDateTime(r.timestamp)}</td>
              <td className="td whitespace-nowrap">{r.hostname}</td>
              <td className="td">{r.service ?? 'n/a'}</td>
              <td className={cx('td font-semibold', LEVEL[r.log_level])}>{r.log_level}</td>
              <td className="td whitespace-nowrap">{r.event_type}</td>
              <td className="td min-w-[18rem] whitespace-normal font-sans text-slate-700">{r.message}{r.packet_loss !== null && r.packet_loss > 0 ? <span className="ml-1 text-slate-400">[loss {r.packet_loss}%]</span> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
