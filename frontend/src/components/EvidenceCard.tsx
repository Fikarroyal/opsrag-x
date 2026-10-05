import { Badge, Meter } from '@/components/ui'
import { cx } from '@/lib/cx'
import { cap, fmtTime } from '@/lib/format'
import type { EvidenceItem } from '@/types/api'

const ROLE: Record<string, string> = { supporting: 'bg-green-50 text-green-700 ring-green-200', contradicting: 'bg-red-50 text-red-700 ring-red-200', context: 'bg-slate-100 text-slate-600 ring-slate-200' }
const KIND: Record<string, string> = { FACT: 'bg-blue-50 text-blue-700 ring-blue-200', INFERENCE: 'bg-violet-50 text-violet-700 ring-violet-200', UNKNOWN: 'bg-amber-50 text-amber-700 ring-amber-200' }

export function EvidenceCard({ e }: { e: EvidenceItem }) {
  return (
    <article className={cx('rounded-md border bg-white p-3', e.role === 'supporting' ? 'border-l-4 border-l-green-500' : e.role === 'contradicting' ? 'border-l-4 border-l-red-500' : 'border-slate-200')}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[11px] text-white">{e.key}</span>
        <Badge>{cap(e.source_type)}</Badge>
        <Badge tone={ROLE[e.role]}>{cap(e.role)}</Badge>
        <Badge tone={KIND[e.kind] ?? KIND.FACT}>{e.kind}</Badge>
        {e.temporal_relation && <Badge>{cap(e.temporal_relation)}</Badge>}
        {e.timestamp && <span className="ml-auto font-mono text-xs text-slate-400">{fmtTime(e.timestamp)}</span>}
      </div>
      <p className="mt-2 text-sm text-slate-700">{e.content}</p>
      <div className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-[11px] text-slate-500 sm:grid-cols-3">
        <div>
          Relevansi <Meter value={e.relevance_score} />
        </div>
        <div>
          Temporal <Meter value={e.temporal_score ?? 0} tone="bg-cyan-500" />
        </div>
        <div>
          Reliabilitas sumber (prioritas {e.priority_rank}) <Meter value={e.reliability} tone="bg-slate-500" />
        </div>
      </div>
      {e.confidence_contribution !== null && e.confidence_contribution !== 0 && (
        <div className="mt-1 text-[11px] text-slate-500">
          Kontribusi ke evidence support hipotesis utama: <span className={e.confidence_contribution > 0 ? 'text-green-700' : 'text-red-700'}>{e.confidence_contribution > 0 ? '+' : ''}{e.confidence_contribution.toFixed(3)}</span>
        </div>
      )}
      {e.tags.length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{e.tags.map((t) => <span key={t} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">{t}</span>)}</div>}
    </article>
  )
}
