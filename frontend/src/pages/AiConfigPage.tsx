import { useMutation, useQuery } from '@tanstack/react-query'
import { Badge, Card, DataState, MeterRow, PageHeader, PropertyList, StatusBadge } from '@/components/ui'
import { useToast } from '@/hooks/toast-context'
import { endpoints } from '@/services/endpoints'

export default function AiConfigPage() {
  const toast = useToast()
  const q = useQuery({ queryKey: ['ai-config'], queryFn: endpoints.aiConfig })
  const llm = useMutation({ mutationFn: endpoints.testLlm, onSuccess: (r) => toast.push(r.ok ? 'success' : 'info', r.message) , onError: (e: Error) => toast.push('error', e.message) })
  const mcp = useMutation({ mutationFn: endpoints.testMcp, onSuccess: (r) => toast.push(r.ok ? 'success' : 'info', r.message), onError: (e: Error) => toast.push('error', e.message) })
  return (
    <>
      <PageHeader title="AI Configuration" subtitle="Konfigurasi efektif (baca saja). Ubah melalui environment (.env) lalu restart backend." actions={<><button type="button" className="btn-secondary" onClick={() => llm.mutate()} disabled={llm.isPending}>Tes LLM</button><button type="button" className="btn-secondary" onClick={() => mcp.mutate()} disabled={mcp.isPending}>Tes MCP</button></>} />
      <DataState query={q} skeletonRows={8}>
        {(c) => (
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title="Mode dan LLM">
              <PropertyList items={[
                { k: 'Mode', v: c.mode === 'llm' ? <Badge tone="bg-green-50 text-green-700 ring-green-200">LLM aktif</Badge> : <Badge tone="bg-amber-50 text-amber-700 ring-amber-200">Fallback tanpa LLM</Badge> },
                { k: 'Penyedia LLM', v: c.llm.provider || 'n/a' },
                { k: 'Model LLM', v: c.llm.model || 'n/a' },
                { k: 'Ketersediaan', v: <StatusBadge status={c.llm.available ? 'available' : 'unavailable'} /> },
              ]} />
              <p className="mt-4 rounded-md bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-500">Tanpa LLM, klasifikasi berbasis aturan, retrieval, diagnostik MCP, dan skoring hipotesis tetap aktif. Laporan memakai template terstruktur.</p>
            </Card>
            <Card title="Embedding">
              <PropertyList items={[
                { k: 'Embedder aktif', v: <span className="font-mono text-xs">{c.embedding.name}</span> },
                { k: 'Model dikonfigurasi', v: <span className="font-mono text-xs">{c.embedding.configured_model}</span> },
                { k: 'Backend', v: c.embedding.backend },
                { k: 'Dimensi', v: c.embedding.dim },
              ]} />
            </Card>
            <Card title="MCP (hanya baca)">
              <PropertyList items={[
                { k: 'URL', v: <span className="font-mono text-xs">{c.mcp.url}</span> },
                { k: 'Transport', v: c.mcp.transport },
                { k: 'Kesehatan', v: <StatusBadge status={c.mcp.healthy ? 'healthy' : 'unavailable'} /> },
                { k: 'Hanya baca', v: c.mcp.read_only ? 'Ya' : 'Tidak' },
              ]} />
              <div className="mt-4 border-t border-slate-100 pt-3">
                <div className="mb-2 text-xs font-medium text-slate-500">Tool tersedia ({c.mcp.tools.length})</div>
                <div className="flex flex-wrap gap-1.5">{c.mcp.tools.map((t) => <span key={t} className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">{t}</span>)}</div>
              </div>
            </Card>
            <Card title="Parameter retrieval dan korelasi">
              <PropertyList items={[
                { k: 'Top K', v: c.top_k },
                { k: 'Half-life historis', v: `${c.history_half_life_days} hari` },
                { k: 'Half-life SOP', v: `${c.sop_half_life_days} hari` },
                { k: 'Half-life log', v: `${c.log_half_life_minutes} menit` },
                { k: 'Jendela korelasi', v: `± ${c.correlation_window_minutes} menit` },
              ]} />
            </Card>
            <Card title="Bobot retrieval">
              {Object.entries(c.retrieval_weights).map(([k, v]) => <MeterRow key={k} label={k} value={v} />)}
            </Card>
            <Card title="Bobot skor hipotesis">
              {Object.entries(c.hypothesis_weights).map(([k, v]) => <MeterRow key={k} label={k} value={v} tone="bg-violet-500" />)}
              <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-500">Kesimpulan diberikan bila confidence minimal {(c.min_confidence_for_root_cause * 100).toFixed(0)}% dan dukungan evidence minimal 30%. Skor ini bukan probabilitas statistik.</p>
            </Card>
          </div>
        )}
      </DataState>
    </>
  )
}
