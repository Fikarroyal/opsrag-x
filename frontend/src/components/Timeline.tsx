import { Badge } from '@/components/ui'
import { cx } from '@/lib/cx'
import { cap, fmtTime } from '@/lib/format'
import type { TimelineItem } from '@/types/api'

const DOT: Record<string, string> = { before_incident: 'bg-amber-500', during_incident: 'bg-red-500', after_incident: 'bg-blue-500', unrelated: 'bg-slate-300' }

export function Timeline({ items, incidentTime }: { items: TimelineItem[]; incidentTime?: string }) {
  return (
    <ol className="relative ml-2 border-l border-slate-200">
      {items.map((t, i) => (
        <li key={`${t.timestamp}-${t.source}-${i}`} className="mb-3 ml-4">
          <span className={cx('absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-white', DOT[t.relation ?? 'unrelated'] ?? 'bg-slate-300')} />
          <div className="flex flex-wrap items-center gap-2">
            <time className="font-mono text-xs font-semibold text-slate-700">{fmtTime(t.timestamp)}</time>
            <Badge>{t.source}</Badge>
            {t.relation && <span className="text-[11px] text-slate-400">{cap(t.relation)}</span>}
            {incidentTime && t.timestamp === incidentTime && <Badge tone="bg-red-50 text-red-700 ring-red-200">Waktu incident</Badge>}
            {t.evidence_key && <span className="font-mono text-[11px] text-slate-400">{t.evidence_key}</span>}
            <span className="ml-auto flex items-center gap-1 text-[11px] text-slate-400" title="Relevansi">
              <span className="inline-block h-1.5 w-12 overflow-hidden rounded bg-slate-100"><span className="block h-full bg-brand-500" style={{ width: `${Math.round(t.relevance * 100)}%` }} /></span>
              {(t.relevance * 100).toFixed(0)}%
            </span>
          </div>
          <p className="mt-0.5 text-sm text-slate-700">{t.event}</p>
        </li>
      ))}
    </ol>
  )
}
