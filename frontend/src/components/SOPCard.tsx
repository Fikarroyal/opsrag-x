import { ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { Badge, StatusBadge } from '@/components/ui'
import type { Sop } from '@/types/api'

const LABEL: Record<string, string> = { tujuan: 'Tujuan', indikasi: 'Indikasi', prasyarat: 'Prasyarat', langkah_investigasi: 'Langkah investigasi', indikator_evidence: 'Indikator evidence', langkah_remediation: 'Langkah remediation', verifikasi: 'Verifikasi', rollback: 'Rollback', catatan: 'Catatan' }

export function SOPCard({ sop }: { sop: Sop }) {
  const [open, setOpen] = useState(false)
  const [ver, setVer] = useState(sop.active_version ?? sop.versions[0]?.version)
  const v = sop.versions.find((x) => x.version === ver)
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2"><span className="font-mono text-sm font-bold text-brand-700">{sop.sop_code}</span>{sop.category && <Badge>{sop.category}</Badge>}</div>
          <h3 className="mt-0.5 text-sm font-semibold text-slate-900">{sop.title}</h3>
        </div>
        <div className="text-right text-xs text-slate-500">
          <div>Versi aktif <strong className="text-slate-800">v{sop.active_version}</strong> <StatusBadge status={sop.status} /></div>
          <div>Berlaku sejak {sop.effective_date}</div>
          <div>Incident relevan (kategori): {sop.relevant_incidents}</div>
        </div>
      </div>
      <button type="button" className="mt-2 flex items-center gap-1 text-xs font-medium text-brand-600" onClick={() => setOpen(!open)}>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />} Detail & riwayat versi ({sop.versions.length})
      </button>
      {open && v && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap gap-1.5">
            {sop.versions.map((x) => (
              <button key={x.version} type="button" onClick={() => setVer(x.version)} className={`rounded-md border px-2 py-1 text-xs ${x.version === ver ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 text-slate-600'}`}>
                v{x.version} · {x.effective_date} · {x.status}
              </button>
            ))}
          </div>
          <dl className="space-y-2">
            {Object.entries(v.sections).map(([k, text]) => (
              <div key={k}><dt className="text-xs font-semibold uppercase tracking-wide text-slate-400">{LABEL[k] ?? k}</dt><dd className="whitespace-pre-line text-sm text-slate-700">{text}</dd></div>
            ))}
          </dl>
        </div>
      )}
    </article>
  )
}
