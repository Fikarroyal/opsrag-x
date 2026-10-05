import { ChevronDown, ChevronUp, Wrench } from 'lucide-react'
import { useState } from 'react'
import { StatusBadge } from '@/components/ui'

export function ToolExecutionCard({ name, purpose, status, ms, args, summary, result, error }: { name: string; purpose?: string | null; status: string; ms?: number | null; args: Record<string, unknown>; summary?: string; result?: Record<string, unknown> | null; error?: string | null }) {
  const [open, setOpen] = useState(false)
  const compact = Object.entries(args).filter(([k]) => k !== 'as_of').map(([k, v]) => `${k}=${String(v)}`).join(', ')
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Wrench className="h-4 w-4 text-slate-400" />
        <span className="font-mono text-sm font-semibold text-slate-800">{name}</span>
        <StatusBadge status={status} />
        <span className="ml-auto text-xs text-slate-400">{ms !== null && ms !== undefined ? `${ms.toFixed(1)} ms` : ''}</span>
      </div>
      {purpose && <p className="mt-1 text-xs text-slate-500">Tujuan: {purpose}</p>}
      <p className="mt-1 break-all font-mono text-[11px] text-slate-400">{compact}</p>
      {summary && <p className="mt-1 text-sm text-slate-700">{summary}</p>}
      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      {result && (
        <>
          <button type="button" className="mt-1 flex items-center gap-1 text-xs text-brand-600" onClick={() => setOpen(!open)}>
            {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />} Hasil mentah (JSON)
          </button>
          {open && <pre className="mt-1 max-h-60 overflow-auto rounded bg-slate-900 p-2 text-[11px] text-slate-100">{JSON.stringify(result, null, 2)}</pre>}
        </>
      )}
    </div>
  )
}
