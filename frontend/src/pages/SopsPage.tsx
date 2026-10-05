import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { SOPCard } from '@/components/SOPCard'
import { Card, DataState, PageHeader, SearchInput, Select } from '@/components/ui'
import { CATEGORIES } from '@/lib/format'
import { endpoints } from '@/services/endpoints'

export default function SopsPage() {
  const [f, setF] = useState({ q: '', category: '', status: '' })
  const q = useQuery({ queryKey: ['sops', f], queryFn: () => endpoints.sops(f) })
  return (
    <>
      <PageHeader title="SOP Library" subtitle="SOP dengan versi, tanggal berlaku dan status. Investigasi memakai versi yang berlaku pada waktu incident." />
      <Card className="mb-4"><div className="grid gap-2 sm:grid-cols-3"><SearchInput value={f.q} onChange={(v) => setF({ ...f, q: v })} placeholder="Cari SOP" /><Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={CATEGORIES} placeholder="Semua kategori" /><Select value={f.status} onChange={(v) => setF({ ...f, status: v })} options={['active', 'superseded', 'scheduled']} placeholder="Semua status versi" /></div></Card>
      <DataState query={q} isEmpty={(d) => d.length === 0} emptyTitle="SOP tidak ditemukan">{(list) => <div className="grid gap-3 xl:grid-cols-2">{list.map((s) => <SOPCard key={s.sop_code} sop={s} />)}</div>}</DataState>
    </>
  )
}
