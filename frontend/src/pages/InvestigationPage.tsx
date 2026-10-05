import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileJson, FileText, Network, RefreshCw, ShieldAlert } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { HistoricalIncidentTable } from '@/components/HistoricalIncidentTable'
import { HypothesisCard } from '@/components/HypothesisCard'
import { InvestigationProgress } from '@/components/InvestigationProgress'
import { Timeline } from '@/components/Timeline'
import { ToolExecutionCard } from '@/components/ToolExecutionCard'
import { Badge, Card, ConfirmDialog, DataState, KeyValue, Meter, PageHeader, SeverityBadge, StatusBadge } from '@/components/ui'
import { useToast } from '@/hooks/toast-context'
import { cap, fmtDateTime, pct } from '@/lib/format'
import { downloadUrl } from '@/services/api'
import { endpoints } from '@/services/endpoints'

const TERMINAL = ['completed', 'failed']
const TYPE_TONE: Record<string, string> = { FACT: 'bg-blue-50 text-blue-700 ring-blue-200', INFERENCE: 'bg-violet-50 text-violet-700 ring-violet-200', UNKNOWN: 'bg-amber-50 text-amber-700 ring-amber-200', HYPOTHESIS: 'bg-indigo-50 text-indigo-700 ring-indigo-200', RECOMMENDATION: 'bg-green-50 text-green-700 ring-green-200' }

export default function InvestigationPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const [replay, setReplay] = useState(false)
  const q = useQuery({ queryKey: ['investigation', id], queryFn: () => endpoints.investigation(id), refetchInterval: (query) => (query.state.data && TERMINAL.includes(query.state.data.status) ? false : 1000) })
  const replayM = useMutation({ mutationFn: () => endpoints.replay(id), onSuccess: (r) => { setReplay(false); toast.push('info', 'Replay investigasi dimulai'); void qc.invalidateQueries({ queryKey: ['investigations'] }); nav(`/investigations/${r.id}`) }, onError: (e: Error) => { setReplay(false); toast.push('error', e.message) } })
  const parent = q.data?.parent_investigation_id
  const cmp = useQuery({ queryKey: ['compare', parent, id], queryFn: () => endpoints.compare(parent as string, id), enabled: !!parent && q.data?.status === 'completed' })
  return (
    <DataState query={q} skeletonRows={8}>
      {(inv) => {
        const r = inv.report
        const done = inv.status === 'completed' && r
        return (
          <>
            <PageHeader title={r ? `Investigasi ${r.incident.ticket_number}` : 'Investigasi berjalan'} subtitle={r?.incident.title ?? 'Menunggu hasil...'} actions={<>
              <StatusBadge status={inv.status} />
              {inv.ai_mode && <Badge tone={inv.ai_mode === 'llm' ? 'bg-green-50 text-green-700 ring-green-200' : 'bg-amber-50 text-amber-700 ring-amber-200'}>{inv.ai_mode === 'llm' ? 'LLM' : 'Mode fallback'}</Badge>}
              <button type="button" className="btn-secondary" onClick={() => setReplay(true)} disabled={!TERMINAL.includes(inv.status)}><RefreshCw className="h-4 w-4" /> Replay</button>
              <a className={`btn-secondary ${done ? '' : 'pointer-events-none opacity-50'}`} href={downloadUrl(`/api/investigations/${id}/export/json`)} download><FileJson className="h-4 w-4" /> Export JSON</a>
              <a className={`btn-secondary ${done ? '' : 'pointer-events-none opacity-50'}`} href={downloadUrl(`/api/investigations/${id}/export/pdf`)} download><FileText className="h-4 w-4" /> Export PDF</a>
            </>} />
            <div className="space-y-4">
              <Card title="Investigation Progress"><InvestigationProgress stages={inv.stages} status={inv.status} /></Card>
              {inv.status === 'failed' && <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700" role="alert"><ShieldAlert className="mr-2 inline h-4 w-4" />Investigasi gagal: {inv.error_message ?? 'kesalahan tidak diketahui'}. Gunakan Replay untuk mencoba lagi.</div>}
              {!TERMINAL.includes(inv.status) && <div className="text-sm text-slate-500">Memperbarui otomatis setiap detik...</div>}
              {cmp.data && <Card title="Perbandingan dengan investigasi asal (replay)"><p className="text-sm text-slate-700">{cmp.data.reproducible ? 'Hasil dapat direproduksi: hipotesis utama, evidence dan confidence identik.' : 'Hasil berbeda dari investigasi asal'} (confidence {pct(cmp.data.confidence_a, 1)} vs {pct(cmp.data.confidence_b, 1)}; tools sama: {cmp.data.same_tools ? 'ya' : 'tidak'}).</p></Card>}
              {done && r && (
                <>
                  <Card title="Incident Summary">
                    <p className="text-sm text-slate-800">{r.incident_summary}</p>
                    {r.ai_narrative && <p className="mt-2 rounded bg-slate-50 p-2 text-sm text-slate-600"><span className="font-semibold">Ringkasan LLM (dibatasi pada fakta di atas): </span>{r.ai_narrative}</p>}
                    <div className="mt-3"><KeyValue items={[
                      { k: 'Kategori', v: <>{cap(r.classification.category)}{r.classification.secondary_category ? <span className="text-slate-400"> / {cap(r.classification.secondary_category)}</span> : null}</> }, { k: 'Severity', v: <SeverityBadge severity={r.classification.severity} /> },
                      { k: 'Cakupan', v: cap(r.classification.affected_scope) }, { k: 'Layanan', v: r.classification.affected_service ?? 'n/a' }, { k: 'Klasifikasi', v: `${r.classification.method} (${pct(r.classification.confidence)})` },
                      { k: 'Waktu incident', v: <span className="font-mono text-xs">{fmtDateTime(r.incident.occurred_at)}</span> }, { k: 'Model', v: r.model_used }, { k: 'Durasi', v: inv.duration_ms ? `${(inv.duration_ms / 1000).toFixed(2)} dtk` : '-' },
                    ]} /></div>
                  </Card>
                  <div className={`rounded-md border p-3 text-sm ${r.root_cause_conclusion.status === 'most_supported' ? 'border-green-200 bg-green-50 text-green-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                    <strong>{r.root_cause_conclusion.status === 'most_supported' ? 'Hipotesis paling didukung evidence: ' : 'Kesimpulan: '}</strong>{r.root_cause_conclusion.description}
                    {r.root_cause_conclusion.status === 'most_supported' && <span>, evidence confidence score {pct(r.root_cause_conclusion.confidence)}. {r.root_cause_conclusion.note}</span>}
                  </div>
                  <Card title="Findings (FACT / INFERENCE / UNKNOWN)"><ul className="space-y-1.5">{r.findings.map((f) => <li key={f.id} className="flex items-start gap-2 text-sm"><Badge tone={TYPE_TONE[f.type]}>{f.type}</Badge><span className="text-slate-700">{f.statement}</span><span className="ml-auto shrink-0 font-mono text-[11px] text-slate-400">{f.evidence_refs.join(', ')}</span></li>)}</ul></Card>
                  <div><h2 className="mb-2 text-sm font-semibold text-slate-800">Root Cause Hypotheses <Badge tone={TYPE_TONE.HYPOTHESIS}>HYPOTHESIS</Badge></h2><div className="space-y-3">{r.root_cause_hypotheses.filter((h, i) => i < 3 || h.status === 'plausible').map((h, i) => <HypothesisCard key={h.id} h={h} rank={i} />)}</div></div>
                  <Card title="Evidence Timeline" actions={<div className="flex gap-3 text-xs"><Link className="text-brand-600" to={`/timeline/${id}`}>Audit timeline</Link><Link className="text-brand-600" to={`/evidence/${id}`}>Evidence explorer</Link></div>}>
                    <Timeline items={r.timeline} incidentTime={r.incident.occurred_at} />
                    {r.correlation.patterns.length > 0 && <div className="mt-3 rounded bg-slate-50 p-3 text-sm"><div className="mb-1 text-xs font-semibold uppercase text-slate-400">Pola korelasi temporal</div>{r.correlation.patterns.map((p) => <div key={p.name} className="mb-1"><span className="font-mono text-xs">{p.name}</span> - onset penyebab {p.cause_onset.slice(11, 19)}, gejala {p.symptom_onset.slice(11, 19)} (jeda {p.lag_seconds.toFixed(0)} dtk) - {p.order_ok ? 'urutan konsisten' : 'URUTAN TIDAK KONSISTEN'}<Meter value={p.correlation_score} label="correlation score" /></div>)}</div>}
                  </Card>
                  <Card title="Tool Execution Log (read-only MCP)"><div className="grid gap-2 lg:grid-cols-2">{r.tools_executed.map((t, i) => <ToolExecutionCard key={`${t.tool}-${i}`} name={t.tool} purpose={t.purpose} status={t.status} ms={t.execution_ms} args={t.arguments} summary={t.summary} error={t.error} />)}</div>
                    <details className="mt-3 text-sm"><summary className="cursor-pointer text-brand-600">Decision trace (ringkas, berbasis evidence)</summary><div className="mt-2 space-y-1 text-slate-700"><p><strong>Klasifikasi:</strong> {JSON.stringify(r.decision_trace.classification)}</p>{r.decision_trace.reasoning_summary.map((x, i) => <p key={i}>- {x}</p>)}{r.decision_trace.selected_tools.map((t, i) => <p key={i}><span className="font-mono">{t.tool}</span> - {t.why} - hasil: {t.result_summary} {t.evidence_generated.length ? `(evidence ${t.evidence_generated.join(', ')})` : ''}</p>)}</div></details>
                  </Card>
                  <Card title="Recommended Remediation"><ol className="space-y-2">{r.recommended_actions.map((a) => <li key={a.order} className="rounded-md border border-slate-200 p-3 text-sm"><div className="flex items-start gap-2"><span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs text-white">{a.order}</span><div><p className="text-slate-800">{a.text}</p><p className="mt-1 text-[11px] text-slate-400">Evidence: {a.evidence_refs.join(', ')}{a.sop_reference ? ` - ${a.sop_reference}` : ''} - memerlukan persetujuan manusia</p></div></div></li>)}</ol>
                    <div className="mt-3 rounded bg-slate-50 p-3 text-sm"><div className="text-xs font-semibold uppercase text-slate-400">Verification</div><ul className="ml-4 list-disc text-slate-700">{r.verification_steps.map((v, i) => <li key={i}>{v}</li>)}</ul><p className="mt-2 text-slate-600"><strong>Diagnostik berikutnya: </strong>{r.next_diagnostic}</p></div>
                  </Card>
                  <Card title="SOP References (versi berlaku saat incident)"><div className="grid gap-2 md:grid-cols-2">{r.sop_reference.map((s) => <div key={s.sop_code} className="rounded-md border border-slate-200 p-3 text-sm"><div className="font-mono font-bold text-brand-700">{s.sop_code} v{s.version}</div><div>{s.title}</div><div className="text-xs text-slate-500">Berlaku {s.effective_date} - relevansi {pct(s.relevance)} - bagian: {[...new Set(s.matched_sections)].join(', ')}</div></div>)}</div>
                    <details className="mt-2 text-xs text-slate-500"><summary className="cursor-pointer text-brand-600">Keputusan pemilihan versi SOP</summary><ul className="mt-1">{r.sop_version_decisions.filter((d) => ['SOP-001', 'SOP-003'].includes(d.sop_code)).map((d, i) => <li key={i}>{d.sop_code} v{d.version} ({d.effective_date}): {d.reason}</li>)}</ul></details></Card>
                  <Card title="Historical Incidents (supporting evidence only)"><HistoricalIncidentTable rows={r.historical_incidents} showSimilarity /><p className="mt-2 text-xs text-slate-400"><Link className="text-brand-600" to={`/historical?investigation=${id}`}>Lihat di halaman Historical Incidents</Link></p></Card>
                  <Card title="Limitations"><ul className="ml-4 list-disc space-y-1 text-sm text-slate-700">{r.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></Card>
                  <div className="flex gap-3 text-sm"><Link className="btn-secondary" to={`/map?investigation=${id}`}><Network className="h-4 w-4" /> Lihat di Infrastructure Map</Link><a className="btn-secondary" href={downloadUrl(`/api/investigations/${id}/export/pdf`)} download><Download className="h-4 w-4" /> PDF</a></div>
                </>
              )}
            </div>
            <ConfirmDialog open={replay} title="Replay investigasi?" busy={replayM.isPending} confirmLabel="Replay" onConfirm={() => replayM.mutate()} onCancel={() => setReplay(false)} message="Investigasi dijalankan ulang untuk incident yang sama dengan konfigurasi saat ini, lalu dapat dibandingkan dengan hasil sebelumnya." />
          </>
        )
      }}
    </DataState>
  )
}
