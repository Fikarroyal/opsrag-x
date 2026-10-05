import { AlertTriangle, Check, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { Badge, Meter, StatusBadge } from '@/components/ui'
import { cx } from '@/lib/cx'
import { cap } from '@/lib/format'
import type { Hypothesis } from '@/types/api'

const COMPONENT_LABEL: Record<string, string> = { evidence: 'Evidence support', temporal: 'Temporal alignment', topology: 'Topology alignment', history: 'Historical similarity', state: 'Current service state', source: 'Source reliability' }

export function HypothesisCard({ h, rank }: { h: Hypothesis; rank: number }) {
  const [open, setOpen] = useState(rank === 0)
  const lead = h.status === 'most_supported'
  return (
    <article className={cx('card p-4', lead && 'border-green-300 ring-1 ring-green-200')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-slate-400">Root cause hypothesis {rank + 1} · {h.id}</div>
          <h3 className="mt-0.5 text-base font-semibold text-slate-900">{h.description}</h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge>{cap(h.category)}</Badge>
          <StatusBadge status={h.status} />
        </div>
      </div>
      <div className="mt-3 max-w-md">
        <div className="mb-0.5 text-xs text-slate-500">Evidence confidence score (bukan probabilitas statistik)</div>
        <Meter value={h.confidence} tone={lead ? 'bg-green-500' : 'bg-brand-500'} />
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-green-700">Supporting evidence</div>
          {h.supporting_evidence.length === 0 ? <p className="text-xs text-slate-400">Tidak ada evidence pendukung langsung.</p> : (
            <ul className="space-y-1">{h.supporting_evidence.slice(0, 6).map((s) => <li key={s.key} className="flex gap-1.5 text-sm text-slate-700"><Check className="mt-0.5 h-4 w-4 shrink-0 text-green-600" /><span><span className="font-mono text-[11px] text-slate-400">{s.key}</span> {s.text}</span></li>)}</ul>
          )}
        </div>
        <div>
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-red-700">Contradicting evidence</div>
          {h.contradicting_evidence.length === 0 ? <p className="text-xs text-slate-400">Tidak ada evidence yang bertentangan.</p> : (
            <ul className="space-y-1">{h.contradicting_evidence.slice(0, 5).map((s) => <li key={s.key} className="flex gap-1.5 text-sm text-slate-700"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" /><span><span className="font-mono text-[11px] text-slate-400">{s.key}</span> {s.text}</span></li>)}</ul>
          )}
        </div>
      </div>
      <button type="button" className="mt-3 flex items-center gap-1 text-xs font-medium text-brand-600" onClick={() => setOpen(!open)}>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />} Mengapa hipotesis ini? (komponen skor & penjelasan)
      </button>
      {open && (
        <div className="mt-2 space-y-3 rounded-md bg-slate-50 p-3 text-sm">
          <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
            {Object.entries(h.components).map(([k, v]) => (
              <div key={k}>
                <div className="text-[11px] text-slate-500">{COMPONENT_LABEL[k] ?? k}</div>
                <Meter value={v} />
              </div>
            ))}
          </div>
          <p className="text-slate-700"><strong>Why: </strong>{h.explainability.why}</p>
          {h.explainability.missing_indicators.length > 0 && <p className="text-slate-600"><strong>Indikator belum terpenuhi: </strong>{h.explainability.missing_indicators.join(', ')}</p>}
          <p className="text-slate-700"><strong>Diagnostik berikutnya untuk mengurangi ketidakpastian: </strong>{h.explainability.next_diagnostic}</p>
        </div>
      )}
    </article>
  )
}
