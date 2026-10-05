import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'
import type { StageState } from '@/types/api'
import { cx } from '@/lib/cx'

const STAGES: { id: string; label: string }[] = [
  { id: 'classification', label: 'Classification' },
  { id: 'sop_retrieval', label: 'SOP Retrieval' },
  { id: 'historical_search', label: 'Historical Search' },
  { id: 'topology_inspection', label: 'Topology Inspection' },
  { id: 'mcp_diagnostics', label: 'MCP Diagnostics' },
  { id: 'log_correlation', label: 'Log Correlation' },
  { id: 'root_cause_analysis', label: 'Root Cause Analysis' },
  { id: 'recommendation', label: 'Recommendation' },
]

export function InvestigationProgress({ stages, status }: { stages: Record<string, StageState>; status: string }) {
  const done = STAGES.filter((s) => stages[s.id]?.status === 'done').length
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-xs text-slate-500">
        <span>
          Progres investigasi: <strong className="text-slate-700">{done}/{STAGES.length}</strong> tahap selesai
        </span>
        <span className="shrink-0 text-[11px] font-medium uppercase tracking-wide">{status.replace(/_/g, ' ')}</span>
      </div>
      <div className="mb-3 h-1 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={STAGES.length} aria-valuenow={done}>
        <div className="h-full rounded-full bg-green-500 transition-all" style={{ width: `${(done / STAGES.length) * 100}%` }} />
      </div>
      <ol className="grid grid-cols-1 gap-2 min-[480px]:grid-cols-2 md:grid-cols-4">
        {STAGES.map((s, i) => {
          const st = stages[s.id]?.status ?? 'pending'
          const detail = stages[s.id]?.detail ?? (st === 'pending' ? 'Menunggu' : '')
          return (
            <li key={s.id} className={cx('min-w-0 overflow-hidden rounded-md border px-2.5 py-2', st === 'done' ? 'border-green-200 bg-green-50' : st === 'running' ? 'border-blue-300 bg-blue-50' : st === 'failed' ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white')}>
              <div className="flex items-start gap-1.5">
                <span className="mt-px shrink-0">
                  {st === 'done' ? <CheckCircle2 className="h-3.5 w-3.5 text-green-600" /> : st === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" /> : st === 'failed' ? <XCircle className="h-3.5 w-3.5 text-red-600" /> : <Circle className="h-3.5 w-3.5 text-slate-300" />}
                </span>
                <span className="min-w-0 text-xs font-semibold leading-tight text-slate-700 [overflow-wrap:anywhere]">
                  <span className="mr-1 font-normal text-slate-400">{i + 1}.</span>{s.label}
                </span>
              </div>
              <div className="mt-1 pl-5 text-[11px] leading-snug text-slate-500 [overflow-wrap:anywhere]" title={detail}>{detail}</div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
