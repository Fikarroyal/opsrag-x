import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { InvestigationPicker } from '@/components/InvestigationPicker'
import { TopologyGraph } from '@/components/TopologyGraph'
import { Card, DataState, PageHeader } from '@/components/ui'
import { endpoints } from '@/services/endpoints'

export default function MapPage() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const inv = sp.get('investigation') ?? undefined
  const topo = useQuery({ queryKey: ['topology'], queryFn: endpoints.topology })
  const detail = useQuery({ queryKey: ['investigation', inv], queryFn: () => endpoints.investigation(inv as string), enabled: !!inv })
  const t = detail.data?.report?.topology
  return (
    <>
      <PageHeader title="Infrastructure Map" subtitle="Topologi: router → core → distribution → access switch → endpoint. Pilih investigasi untuk menyorot jalur dan perangkat terdampak." actions={<InvestigationPicker value={inv} onChange={(v) => nav(v ? `/map?investigation=${v}` : '/map')} />} />
      <Card>
        <DataState query={topo}>{(d) => <TopologyGraph topo={d} highlightPath={t?.path ?? []} affectedHosts={t?.affected_hosts ?? []} />}</DataState>
      </Card>
      {t && <Card title="Konteks topologi investigasi" className="mt-4"><ul className="space-y-1 text-sm text-slate-700"><li>Jalur: <span className="font-mono">{t.path.join(' -> ') || '-'}</span></li><li>Switch akses bersama: <strong>{t.shared_access_switch ?? 'tidak ada'}</strong>{t.uplink ? ` (uplink ${t.uplink.interface} -> ${t.uplink.peer})` : ''}</li><li>Cakupan terobservasi: {t.scope_level} ({t.impact_units.join(', ') || '-'})</li><li>Endpoint terdampak: {t.affected_hosts.join(', ') || '-'}</li></ul></Card>}
    </>
  )
}
