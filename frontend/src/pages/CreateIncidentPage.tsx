import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, PageHeader } from '@/components/ui'
import { useToast } from '@/hooks/toast-context'
import { SERVICES, UNITS, toLocalInput } from '@/lib/format'
import { ApiError } from '@/services/api'
import { endpoints } from '@/services/endpoints'

const EMPTY = { title: '', description: '', reported_by: '', affected_unit: '', affected_device: '', affected_service: '', occurred_at: '' }

export default function CreateIncidentPage() {
  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const scenarios = useQuery({ queryKey: ['scenarios'], queryFn: endpoints.scenarios })
  const m = useMutation({
    mutationFn: () => endpoints.createIncident({ title: form.title.trim(), description: form.description.trim(), reported_by: form.reported_by || undefined, affected_unit: form.affected_unit || undefined, affected_device: form.affected_device || undefined, affected_service: form.affected_service || undefined, occurred_at: form.occurred_at ? `${form.occurred_at}:00` : undefined }),
    onSuccess: (inc) => { void qc.invalidateQueries({ queryKey: ['incidents'] }); toast.push('success', `Incident ${inc.ticket_number} dibuat (${inc.category}/${inc.severity})`); nav(`/incidents/${inc.id}`) },
    onError: (e: Error) => {
      if (e instanceof ApiError && e.details) setErrors(Object.fromEntries(e.details.map((d) => [d.field, d.message])))
      toast.push('error', e.message)
    },
  })
  const set = (k: keyof typeof EMPTY) => (v: string) => setForm((f) => ({ ...f, [k]: v }))
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const err: Record<string, string> = {}
    if (form.title.trim().length < 5) err.title = 'Judul minimal 5 karakter'
    if (form.description.trim().length < 10) err.description = 'Deskripsi minimal 10 karakter'
    if (form.affected_device && !/^[A-Za-z0-9\-.]+$/.test(form.affected_device)) err.affected_device = 'Hanya huruf, angka, tanda minus, dan titik'
    setErrors(err)
    if (Object.keys(err).length === 0) m.mutate()
  }
  const field = (k: keyof typeof EMPTY, label: string, input: React.ReactNode) => (
    <div><label className="label" htmlFor={k}>{label}</label>{input}{errors[k] && <p className="mt-1 text-xs text-red-600">{errors[k]}</p>}</div>
  )
  return (
    <>
      <PageHeader title="Create Incident" subtitle="Laporkan gangguan infrastruktur TI. Jangan memasukkan data pasien." />
      <div className="grid gap-4 lg:grid-cols-3">
        <form onSubmit={submit} className="card space-y-4 p-4 lg:col-span-2" noValidate>
          {field('title', 'Judul', <input id="title" className="input" value={form.title} onChange={(e) => set('title')(e.target.value)} placeholder="Contoh: SIMRS tidak dapat dibuka dari Poli 3" />)}
          {field('description', 'Deskripsi', <textarea id="description" className="input min-h-[110px]" value={form.description} onChange={(e) => set('description')(e.target.value)} placeholder="Gejala, unit terdampak, kapan mulai (mis. sekitar pukul 09:42)" />)}
          <div className="grid gap-4 sm:grid-cols-2">
            {field('affected_unit', 'Unit terdampak (opsional)', <select id="affected_unit" className="input" value={form.affected_unit} onChange={(e) => set('affected_unit')(e.target.value)}><option value="">Otomatis dari deskripsi</option>{UNITS.map((u) => <option key={u}>{u}</option>)}</select>)}
            {field('affected_service', 'Layanan (opsional)', <select id="affected_service" className="input" value={form.affected_service} onChange={(e) => set('affected_service')(e.target.value)}><option value="">Otomatis</option>{SERVICES.map((u) => <option key={u}>{u}</option>)}</select>)}
            {field('affected_device', 'Perangkat (opsional)', <input id="affected_device" className="input" value={form.affected_device} onChange={(e) => set('affected_device')(e.target.value)} placeholder="PC-POLI3-001" />)}
            {field('occurred_at', 'Waktu mulai gangguan', <input id="occurred_at" type="datetime-local" className="input" value={form.occurred_at} onChange={(e) => set('occurred_at')(e.target.value)} />)}
            {field('reported_by', 'Pelapor (opsional)', <input id="reported_by" className="input" value={form.reported_by} onChange={(e) => set('reported_by')(e.target.value)} />)}
          </div>
          <p className="text-xs text-slate-500">Catatan: data log dan diagnostik tersedia untuk 20-28 September 2026. Pilih waktu pada rentang tersebut agar investigasi menemukan evidence; di luar rentang hasilnya akan "evidence tidak mencukupi".</p>
          <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => { setForm(EMPTY); setErrors({}) }}>Reset</button><button type="submit" className="btn-primary" disabled={m.isPending}>{m.isPending ? 'Menyimpan...' : 'Buat incident'}</button></div>
        </form>
        <Card title="Isi dari skenario">
          {scenarios.isPending ? <p className="text-sm text-slate-400">Memuat...</p> : scenarios.isError ? <p className="text-sm text-red-600">{scenarios.error.message}</p> : (
            <ul className="space-y-2">
              {scenarios.data.filter((s) => s.prefill).map((s) => (
                <li key={s.id}><button type="button" className="w-full rounded-md border border-slate-200 p-2.5 text-left hover:border-brand-500 hover:bg-brand-50"
                  onClick={() => { const p = s.prefill!; setForm({ ...EMPTY, title: p.title, description: p.description, affected_unit: p.affected_unit && p.affected_unit !== 'Semua Unit' ? p.affected_unit : '', affected_service: p.affected_service ?? '', occurred_at: toLocalInput(p.occurred_at) }); setErrors({}) }}>
                  <div className="text-sm font-medium text-slate-800">{s.id}. {s.name}</div><div className="text-xs text-slate-500">{s.description}</div></button></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  )
}
