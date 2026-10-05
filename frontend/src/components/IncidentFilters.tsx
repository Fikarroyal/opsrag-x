import { SearchInput, Select } from '@/components/ui'
import { CATEGORIES, UNITS } from '@/lib/format'

export interface IncidentFilterState { q: string; status: string; severity: string; category: string; unit: string }

export function IncidentFilters({ value, onChange }: { value: IncidentFilterState; onChange: (v: IncidentFilterState) => void }) {
  const set = (k: keyof IncidentFilterState) => (v: string) => onChange({ ...value, [k]: v })
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
      <SearchInput value={value.q} onChange={set('q')} placeholder="Cari ticket/judul/deskripsi" />
      <Select value={value.status} onChange={set('status')} options={['open', 'investigating', 'resolved', 'closed']} placeholder="Semua status" />
      <Select value={value.severity} onChange={set('severity')} options={['low', 'medium', 'high', 'critical']} placeholder="Semua severity" />
      <Select value={value.category} onChange={set('category')} options={CATEGORIES} placeholder="Semua kategori" />
      <Select value={value.unit} onChange={set('unit')} options={UNITS} placeholder="Semua unit" />
    </div>
  )
}
