import { useMemo, useState } from 'react'
import { cx } from '@/lib/cx'
import type { TopoNode, Topology } from '@/types/api'

interface Pos { x: number; y: number }
interface Item { id: string; label: string; sub: string; node?: TopoNode; count?: number; affected?: number }

const ROW_Y: Record<string, number> = { server: 50, router: 150, core_switch: 240, distribution_switch: 330, access_switch: 430, endpoints: 540 }
const W = 112
const H = 46

export function TopologyGraph({ topo, highlightPath = [], affectedHosts = [] }: { topo: Topology; highlightPath?: string[]; affectedHosts?: string[] }) {
  const [selected, setSelected] = useState<TopoNode | null>(null)
  const layout = useMemo(() => {
    const by = (t: string) => topo.nodes.filter((n) => n.device_type === t).sort((a, b) => a.hostname.localeCompare(b.hostname))
    const rows: Record<string, Item[]> = {
      server: by('server').map((n) => ({ id: n.hostname, label: n.hostname, sub: n.ip, node: n })), router: by('router').map((n) => ({ id: n.hostname, label: n.hostname, sub: n.ip, node: n })),
      core_switch: by('core_switch').map((n) => ({ id: n.hostname, label: n.hostname, sub: n.ip, node: n })), distribution_switch: by('distribution_switch').map((n) => ({ id: n.hostname, label: n.hostname, sub: n.ip, node: n })),
      access_switch: by('access_switch').map((n) => ({ id: n.hostname, label: n.hostname, sub: n.ip, node: n })),
    }
    const endpointsByAccess = new Map<string, TopoNode[]>()
    topo.edges.forEach((e) => {
      const a = topo.nodes.find((n) => n.hostname === e.source), b = topo.nodes.find((n) => n.hostname === e.target)
      if (a && b && b.device_type === 'access_switch' && (a.device_type === 'pc' || a.device_type === 'printer')) endpointsByAccess.set(b.hostname, [...(endpointsByAccess.get(b.hostname) ?? []), a])
    })
    const aff = new Set(affectedHosts)
    rows.endpoints = rows.access_switch.map((s) => {
      const eps = endpointsByAccess.get(s.id) ?? []
      return { id: `${s.id}::eps`, label: `${eps.length} endpoint`, sub: eps[0]?.unit ?? '', count: eps.length, affected: eps.filter((e) => aff.has(e.hostname)).length }
    })
    const width = Math.max(1100, rows.access_switch.length * (W + 18))
    const pos = new Map<string, Pos>()
    Object.entries(rows).forEach(([row, items]) => items.forEach((it, i) => pos.set(it.id, { x: ((i + 0.5) * width) / items.length, y: ROW_Y[row] })))
    return { rows, pos, width }
  }, [topo, affectedHosts])

  const hl = new Set(highlightPath)
  const hlEdges = new Set(highlightPath.slice(1).map((h, i) => [highlightPath[i], h].sort().join('|')))
  const accessOfAffected = new Set(layout.rows.access_switch.filter((s) => highlightPath.includes(s.id)).map((s) => s.id))
  const edges: { a: string; b: string; hl: boolean }[] = []
  topo.edges.forEach((e) => {
    const na = topo.nodes.find((n) => n.hostname === e.source), nb = topo.nodes.find((n) => n.hostname === e.target)
    if (!na || !nb || na.device_type === 'pc' || na.device_type === 'printer') return
    edges.push({ a: e.source, b: e.target, hl: hlEdges.has([e.source, e.target].sort().join('|')) })
  })
  layout.rows.access_switch.forEach((s) => edges.push({ a: s.id, b: `${s.id}::eps`, hl: accessOfAffected.has(s.id) && affectedHosts.length > 0 }))

  const stroke = (item: Item) => (item.affected ? '#dc2626' : item.node && hl.has(item.node.hostname) ? '#ea580c' : '#cbd5e1')
  return (
    <div>
      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
        <svg viewBox={`0 0 ${layout.width} 600`} className="min-w-[900px]" role="img" aria-label="Topologi jaringan">
          {edges.map((e, i) => {
            const p = layout.pos.get(e.a), q = layout.pos.get(e.b)
            return p && q ? <line key={i} x1={p.x} y1={p.y + H / 2} x2={q.x} y2={q.y - H / 2} stroke={e.hl ? '#dc2626' : '#cbd5e1'} strokeWidth={e.hl ? 3 : 1.2} /> : null
          })}
          {Object.values(layout.rows).flat().map((it) => {
            const p = layout.pos.get(it.id)
            if (!p) return null
            const isEp = it.id.endsWith('::eps')
            const status = it.node?.status ?? 'healthy'
            return (
              <g key={it.id} transform={`translate(${p.x - W / 2},${p.y - H / 2})`} onClick={() => it.node && setSelected(it.node)} className={cx(it.node && 'cursor-pointer')}>
                <title>{it.node ? `${it.node.hostname} | ${it.node.ip} | ${it.node.device_type} | VLAN ${it.node.vlan} | ${it.node.unit} | ${status}` : `${it.label} ${it.sub}${it.affected ? ` (${it.affected} terdampak)` : ''}`}</title>
                <rect width={W} height={H} rx={7} fill={it.affected ? '#fef2f2' : it.node && hl.has(it.node.hostname) ? '#fff7ed' : isEp ? '#f8fafc' : '#ffffff'} stroke={stroke(it)} strokeWidth={it.affected || (it.node && hl.has(it.node.hostname)) ? 2.5 : 1.2} strokeDasharray={isEp ? '4 3' : undefined} />
                <text x={W / 2} y={isEp ? 20 : 18} textAnchor="middle" className="fill-slate-800 text-[11px] font-semibold">{it.label}</text>
                <text x={W / 2} y={isEp ? 35 : 32} textAnchor="middle" className="fill-slate-500 text-[9.5px]">{isEp ? `${it.sub}${it.affected ? ` · ${it.affected} terdampak` : ''}` : `${it.sub}${it.node ? ` - V${it.node.vlan}` : ''}`}</text>
                {!isEp && <circle cx={W - 9} cy={9} r={4} fill={status === 'healthy' ? '#16a34a' : status === 'degraded' ? '#f59e0b' : '#dc2626'} />}
              </g>
            )
          })}
        </svg>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-500">
        <span className="flex items-center gap-1"><span className="inline-block h-3 w-6 rounded border-2 border-red-600 bg-red-50" /> Jalur/endpoint terkait incident</span>
        <span className="flex items-center gap-1"><span className="inline-block h-3 w-6 rounded border border-dashed border-slate-400" /> Kelompok endpoint per switch akses</span>
        <span>Klik node untuk detail.</span>
      </div>
      {selected && (
        <dl className="card mt-3 grid grid-cols-2 gap-3 p-3 text-sm sm:grid-cols-5">
          {[['Hostname', selected.hostname], ['IP', selected.ip], ['Status', selected.status], ['Unit', selected.unit], ['VLAN', `${selected.vlan} (${topo.vlans[String(selected.vlan)] ?? 'n/a'})`]].map(([k, v]) => <div key={k}><dt className="text-xs uppercase text-slate-400">{k}</dt><dd className="font-medium text-slate-800">{v}</dd></div>)}
        </dl>
      )}
    </div>
  )
}
