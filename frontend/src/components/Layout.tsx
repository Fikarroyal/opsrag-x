import { useQuery } from '@tanstack/react-query'
import { Activity, Bot, Boxes, BrainCircuit, ChevronDown, FileSearch, History, LayoutDashboard, LineChart, ListTree, LogOut, Menu, Monitor, Network, PlusCircle, ScrollText, ServerCog, Settings2, Siren, Stethoscope, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/auth-context'
import { Badge } from '@/components/ui'
import { cx } from '@/lib/cx'
import { endpoints } from '@/services/endpoints'

const NAV: { group: string; items: { to: string; label: string; icon: typeof Activity }[] }[] = [
  { group: 'Operasi', items: [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard }, { to: '/incidents', label: 'Incidents', icon: Siren }, { to: '/incidents/new', label: 'Create Incident', icon: PlusCircle },
  ] },
  { group: 'AI Investigation', items: [
    { to: '/investigations', label: 'AI Investigation', icon: BrainCircuit }, { to: '/timeline', label: 'Investigation Timeline', icon: ListTree }, { to: '/evidence', label: 'Evidence Explorer', icon: FileSearch },
    { to: '/historical', label: 'Historical Incidents', icon: History }, { to: '/analytics', label: 'Investigation Analytics', icon: LineChart },
  ] },
  { group: 'Infrastruktur', items: [
    { to: '/map', label: 'Infrastructure Map', icon: Network }, { to: '/devices', label: 'Device Inventory', icon: Monitor }, { to: '/servers', label: 'Server Monitoring', icon: ServerCog },
    { to: '/services', label: 'Service Monitoring', icon: Boxes }, { to: '/logs', label: 'Log Explorer', icon: ScrollText },
  ] },
  { group: 'Pengetahuan & Konfigurasi', items: [{ to: '/sops', label: 'SOP Library', icon: Stethoscope }, { to: '/ai-config', label: 'AI Configuration', icon: Settings2 }] },
]

function HealthPill() {
  const q = useQuery({ queryKey: ['health'], queryFn: endpoints.health, refetchInterval: 30000, retry: false })
  if (q.isError) return <Badge tone="bg-red-50 text-red-700 ring-red-200">API offline</Badge>
  if (!q.data) return <Badge>Memeriksa...</Badge>
  const tone = q.data.status === 'healthy' ? 'bg-green-50 text-green-700 ring-green-200' : q.data.status === 'degraded' ? 'bg-amber-50 text-amber-700 ring-amber-200' : 'bg-red-50 text-red-700 ring-red-200'
  return (
    <div className="flex items-center gap-2">
      <Badge tone={tone}>System {q.data.status}</Badge>
      <span className="hidden text-xs text-slate-500 md:inline" title={`DB ${q.data.database} · RAG ${q.data.rag} · MCP ${q.data.mcp} · LLM ${q.data.llm}`}>
        {q.data.mode === 'llm' ? 'LLM aktif' : 'Mode fallback (tanpa LLM)'}
      </span>
    </div>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  if (!user) return null
  const initial = user.name.trim().charAt(0).toUpperCase() || '?'
  return (
    <div className="relative" ref={ref}>
      <button type="button" className="flex items-center gap-2 rounded-md py-1 pl-1 pr-2.5 hover:bg-slate-100" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">{initial}</span>
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-slate-700 sm:inline">{user.name}</span>
        <ChevronDown className="h-4 w-4 text-slate-400" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-64 rounded-lg border border-slate-200 bg-white p-1.5 shadow-lg">
          <div className="border-b border-slate-100 px-3 py-2.5">
            <div className="truncate text-sm font-semibold text-slate-900">{user.name}</div>
            <div className="truncate text-xs text-slate-500">{user.email}</div>
            <div className="mt-1.5"><Badge>{user.role.replace('_', ' ')}</Badge></div>
          </div>
          <button type="button" role="menuitem" className="mt-1 flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
            onClick={async () => { setOpen(false); await logout(); nav('/login', { replace: true }) }}>
            <LogOut className="h-4 w-4" /> Keluar
          </button>
        </div>
      )}
    </div>
  )
}

export function Layout() {
  const [open, setOpen] = useState(false)
  return (
    <div className="flex min-h-screen">
      <aside className={cx('fixed inset-y-0 left-0 z-40 w-64 transform overflow-y-auto bg-ink-900 text-slate-300 transition-transform lg:static lg:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')}>
        <div className="flex items-center gap-2 px-4 py-4">
          <Bot className="h-7 w-7 text-brand-100" />
          <div>
            <div className="text-base font-semibold text-white">OpsRAG-X</div>
            <div className="text-[11px] leading-tight text-slate-400">Incident Investigation Agent</div>
          </div>
          <button type="button" className="ml-auto lg:hidden" onClick={() => setOpen(false)} aria-label="Tutup menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="px-2 pb-6">
          {NAV.map((g) => (
            <div key={g.group} className="mb-3">
              <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">{g.group}</div>
              {g.items.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === '/' || i.to === '/incidents'} onClick={() => setOpen(false)}
                  className={({ isActive }) => cx('flex items-center gap-2.5 rounded-md px-3 py-2 text-sm', isActive ? 'bg-brand-600 text-white' : 'hover:bg-ink-800 hover:text-white')}>
                  <i.icon className="h-4 w-4" /> {i.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2.5 backdrop-blur">
          <button type="button" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Buka menu"><Menu className="h-5 w-5" /></button>
          <div className="flex items-center gap-3 text-sm"><span className="font-semibold text-slate-800">RS Yogyakarta</span><span className="h-4 w-px bg-slate-300" aria-hidden /><span className="text-slate-500">IT Operations</span></div>
          <div className="ml-auto flex items-center gap-4"><HealthPill /><UserMenu /></div>
        </header>
        <main className="min-w-0 flex-1 p-4 lg:p-6"><Outlet /></main>
        <footer className="border-t border-slate-200 px-6 py-3 text-xs text-slate-400">Seluruh data bersifat sintetis. Sistem ini adalah investigation agent (read-only): rekomendasi memerlukan verifikasi IT Support.</footer>
      </div>
    </div>
  )
}
