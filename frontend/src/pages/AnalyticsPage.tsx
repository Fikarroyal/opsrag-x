import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Play } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card, DataState, PageHeader, StatCard } from '@/components/ui'
import { useToast } from '@/hooks/toast-context'
import { CHART_COLORS, fmtDateTime, num } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

const METRICS: { key: string; label: string; pct?: boolean }[] = [
  { key: 'classification_accuracy', label: 'Classification accuracy', pct: true }, { key: 'severity_accuracy', label: 'Severity accuracy', pct: true }, { key: 'precision_at_k', label: 'Retrieval Precision@K', pct: true },
  { key: 'recall_at_k', label: 'Retrieval Recall@K (norm.)', pct: true }, { key: 'historical_similarity', label: 'Historical incident similarity', pct: true }, { key: 'sop_hit_rate', label: 'SOP hit rate', pct: true },
  { key: 'tool_selection_f1', label: 'Tool selection (F1)', pct: true }, { key: 'root_cause_agreement', label: 'Root cause agreement', pct: true }, { key: 'evidence_coverage', label: 'Evidence coverage', pct: true }, { key: 'avg_time_s', label: 'Avg investigation time (s)' },
]

export default function AnalyticsPage() {
  const toast = useToast()
  const qc = useQueryClient()
  const bench = useQuery({ queryKey: ['benchmark'], queryFn: endpoints.benchmark, refetchInterval: (q) => (q.state.data?.run_state?.status === 'running' ? 3000 : false) })
  const live = useQuery({ queryKey: ['inv-analytics'], queryFn: endpoints.investigationAnalytics })
  const run = useMutation({ mutationFn: endpoints.runBenchmark, onSuccess: () => { toast.push('info', 'Benchmark berjalan di background (sekitar 30-60 detik)'); void qc.invalidateQueries({ queryKey: ['benchmark'] }) }, onError: (e: Error) => toast.push('error', e.message) })
  const running = bench.data?.run_state?.status === 'running' || run.isPending
  return (
    <>
      <PageHeader title="Investigation Analytics" subtitle="Metrik riset dihitung dari eksekusi benchmark sintetis yang nyata (bukan angka tetap)" actions={<button type="button" className="btn-primary" disabled={running} onClick={() => run.mutate()}><Play className="h-4 w-4" /> {running ? 'Benchmark berjalan...' : 'Jalankan benchmark'}</button>} />
      <div className="space-y-4">
        <DataState query={live}>{(a) => (<div className="grid grid-cols-2 gap-3 lg:grid-cols-5"><StatCard label="Investigasi" value={a.total} /><StatCard label="Selesai" value={a.completed} tone="green" /><StatCard label="Gagal" value={a.failed} tone="red" /><StatCard label="Rata-rata durasi" value={a.avg_duration_ms ? `${(a.avg_duration_ms / 1000).toFixed(2)} s` : '-'} /><StatCard label="Rata-rata confidence" value={a.avg_confidence !== null ? `${(a.avg_confidence * 100).toFixed(0)}%` : '-'} hint="evidence confidence score" /></div>)}</DataState>
        <DataState query={bench}>
          {(b) => !b.available || !b.experiments ? <Card><p className="text-sm text-slate-600">{b.message}</p></Card> : (
            <>
              <Card title={`Experiment A-D (${b.benchmark_size} incident, K=${b.k}, embedding ${b.embedding}, classifier ${b.classifier}, dihasilkan ${fmtDateTime(b.generated_at)})`}>
                <div className="overflow-x-auto"><table className="min-w-full divide-y divide-slate-100"><thead className="bg-slate-50"><tr><th className="th">Metrik</th>{b.experiments.map((e) => <th key={e.id} className="th" title={e.description}>{e.id}: {e.name}</th>)}</tr></thead><tbody className="divide-y divide-slate-100">
                  {METRICS.map((m) => <tr key={m.key}><td className="td font-medium">{m.label}</td>{b.experiments!.map((e) => { const v = e.metrics[m.key]; return <td key={e.id} className="td tabular-nums">{v === null || v === undefined ? <span className="text-slate-300">n/a</span> : m.pct ? `${(v * 100).toFixed(1)}%` : num(v, 3)}</td> })}</tr>)}
                </tbody></table></div>
              </Card>
              <Card title="Perbandingan konfigurasi (chart)"><ResponsiveContainer width="100%" height={300}><BarChart data={METRICS.filter((m) => m.pct).map((m) => ({ metric: m.label.replace('Retrieval ', '').replace(' accuracy', ' acc.'), ...Object.fromEntries(b.experiments!.map((e) => [e.id, e.metrics[m.key] === null ? 0 : Number(((e.metrics[m.key] as number) * 100).toFixed(1))])) }))}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="metric" tick={{ fontSize: 10 }} interval={0} angle={-15} height={60} /><YAxis unit="%" domain={[0, 100]} /><Tooltip /><Legend />{b.experiments.map((e, i) => <Bar key={e.id} dataKey={e.id} name={`${e.id}: ${e.name}`} fill={CHART_COLORS[i]} />)}</BarChart></ResponsiveContainer><p className="mt-1 text-xs text-slate-400">n/a ditampilkan sebagai 0 pada chart; pada tabel metrik yang tidak berlaku ditulis n/a.</p></Card>
              <Card title="Catatan metodologi"><ul className="ml-4 list-disc space-y-1 text-sm text-slate-700">{b.notes?.map((n, i) => <li key={i}>{n}</li>)}</ul></Card>
            </>
          )}
        </DataState>
      </div>
    </>
  )
}
