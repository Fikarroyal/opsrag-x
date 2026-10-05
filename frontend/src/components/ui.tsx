import type { UseQueryResult } from '@tanstack/react-query'
import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, RefreshCw, Search, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { useDebounce } from '@/hooks/useDebounce'
import { cx } from '@/lib/cx'
import { cap } from '@/lib/format'

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Card({ title, actions, children, className, dense }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string; dense?: boolean }) {
  return (
    <section className={cx('card min-w-0', className)}>
      {(title || actions) && (
        <header className={cx('flex items-center justify-between gap-2 border-b border-slate-100', dense ? 'px-3 py-2' : 'px-4 py-3')}>
          {title && <h2 className={cx('truncate font-semibold text-slate-800', dense ? 'text-[13px]' : 'text-sm')}>{title}</h2>}
          {actions}
        </header>
      )}
      <div className={dense ? 'p-3' : 'p-4'}>{children}</div>
    </section>
  )
}

export function StatCard({ label, value, hint, icon, tone = 'slate' }: { label: string; value: ReactNode; hint?: string; icon?: ReactNode; tone?: 'slate' | 'blue' | 'red' | 'green' | 'amber' }) {
  const tones = { slate: 'bg-slate-100 text-slate-600', blue: 'bg-blue-50 text-blue-600', red: 'bg-red-50 text-red-600', green: 'bg-green-50 text-green-600', amber: 'bg-amber-50 text-amber-600' }
  return (
    <div className="card flex min-w-0 items-center gap-3 px-3 py-2.5">
      {icon && <div className={cx('flex h-9 w-9 shrink-0 items-center justify-center rounded-md', tones[tone])}>{icon}</div>}
      <div className="min-w-0">
        <div className="text-xs font-medium leading-tight text-slate-500">{label}</div>
        <div className="text-xl font-semibold leading-tight text-slate-900">{value}</div>
        {hint && <div className="text-[11px] leading-tight text-slate-400">{hint}</div>}
      </div>
    </div>
  )
}

const STATUS_TONE: Record<string, string> = {
  open: 'bg-amber-50 text-amber-700 ring-amber-200', investigating: 'bg-blue-50 text-blue-700 ring-blue-200', resolved: 'bg-green-50 text-green-700 ring-green-200',
  closed: 'bg-slate-100 text-slate-600 ring-slate-200', queued: 'bg-slate-100 text-slate-600 ring-slate-200', running: 'bg-blue-50 text-blue-700 ring-blue-200',
  collecting_evidence: 'bg-blue-50 text-blue-700 ring-blue-200', analyzing: 'bg-blue-50 text-blue-700 ring-blue-200', generating_report: 'bg-blue-50 text-blue-700 ring-blue-200',
  completed: 'bg-green-50 text-green-700 ring-green-200', failed: 'bg-red-50 text-red-700 ring-red-200', healthy: 'bg-green-50 text-green-700 ring-green-200',
  online: 'bg-green-50 text-green-700 ring-green-200', degraded: 'bg-amber-50 text-amber-700 ring-amber-200', down: 'bg-red-50 text-red-700 ring-red-200',
  warning: 'bg-amber-50 text-amber-700 ring-amber-200', critical: 'bg-red-50 text-red-700 ring-red-200', unknown: 'bg-slate-100 text-slate-500 ring-slate-200',
  unhealthy: 'bg-red-50 text-red-700 ring-red-200', unavailable: 'bg-amber-50 text-amber-700 ring-amber-200', available: 'bg-green-50 text-green-700 ring-green-200',
  success: 'bg-green-50 text-green-700 ring-green-200', error: 'bg-red-50 text-red-700 ring-red-200', timeout: 'bg-amber-50 text-amber-700 ring-amber-200',
  active: 'bg-green-50 text-green-700 ring-green-200', superseded: 'bg-slate-100 text-slate-500 ring-slate-200', scheduled: 'bg-violet-50 text-violet-700 ring-violet-200',
  most_supported: 'bg-green-50 text-green-700 ring-green-200', plausible: 'bg-blue-50 text-blue-700 ring-blue-200', unlikely: 'bg-slate-100 text-slate-500 ring-slate-200',
  contradicted: 'bg-red-50 text-red-700 ring-red-200', insufficient_evidence: 'bg-amber-50 text-amber-700 ring-amber-200', inconclusive: 'bg-amber-50 text-amber-700 ring-amber-200',
  running_svc: 'bg-green-50 text-green-700 ring-green-200',
}

export function Badge({ children, tone, className }: { children: ReactNode; tone?: string; className?: string }) {
  return <span className={cx('inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset', tone ?? 'bg-slate-100 text-slate-600 ring-slate-200', className)}>{children}</span>
}

export function StatusBadge({ status }: { status?: string | null }) {
  const s = status ?? 'unknown'
  return <Badge tone={STATUS_TONE[s] ?? STATUS_TONE.unknown}>{cap(s)}</Badge>
}

const SEV_TONE: Record<string, string> = {
  low: 'bg-slate-100 text-slate-600 ring-slate-200', medium: 'bg-blue-50 text-blue-700 ring-blue-200', high: 'bg-orange-50 text-orange-700 ring-orange-200', critical: 'bg-red-50 text-red-700 ring-red-200',
}
export function SeverityBadge({ severity }: { severity?: string | null }) {
  return <Badge tone={SEV_TONE[severity ?? ''] ?? STATUS_TONE.unknown}>{cap(severity)}</Badge>
}

export function LoadingSkeleton({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx('animate-pulse space-y-3', className)} aria-busy="true" aria-label="Memuat data">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-5 rounded bg-slate-200" style={{ width: `${95 - ((i * 13) % 40)}%` }} />
      ))}
    </div>
  )
}

export function EmptyState({ title = 'Tidak ada data', description, action }: { title?: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <Inbox className="h-8 w-8 text-slate-300" />
      <div className="text-sm font-medium text-slate-600">{title}</div>
      {description && <div className="max-w-md text-xs text-slate-400">{description}</div>}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-red-200 bg-red-50 p-6 text-center" role="alert">
      <AlertTriangle className="h-6 w-6 text-red-500" />
      <div className="text-sm font-medium text-red-700">Gagal memuat data</div>
      <div className="max-w-lg text-xs text-red-600">{error.message}</div>
      {onRetry && (
        <button type="button" className="btn-secondary mt-1" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" /> Coba lagi
        </button>
      )}
    </div>
  )
}

export function DataState<T>({ query, children, isEmpty, emptyTitle, emptyDescription, skeletonRows }: { query: UseQueryResult<T, Error>; children: (data: T) => ReactNode; isEmpty?: (d: T) => boolean; emptyTitle?: string; emptyDescription?: string; skeletonRows?: number }) {
  if (query.isPending) return <LoadingSkeleton rows={skeletonRows} />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  if (isEmpty?.(query.data)) return <EmptyState title={emptyTitle} description={emptyDescription} />
  return <>{children(query.data)}</>
}

export function SearchInput({ value, onChange, placeholder = 'Cari...' }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [local, setLocal] = useState(value)
  const debounced = useDebounce(local)
  useEffect(() => {
    if (debounced !== value) onChange(debounced)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])
  useEffect(() => setLocal(value), [value])
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-400" />
      <input className="input pl-8 pr-8" value={local} onChange={(e) => setLocal(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      {local && (
        <button type="button" className="absolute right-2 top-2.5 text-slate-400 hover:text-slate-600" onClick={() => setLocal('')} aria-label="Hapus pencarian">
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

export function DateRangeFilter({ start, end, onChange }: { start: string; end: string; onChange: (start: string, end: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <input type="datetime-local" className="input" value={start} onChange={(e) => onChange(e.target.value, end)} aria-label="Mulai" />
      <span className="text-slate-400">-</span>
      <input type="datetime-local" className="input" value={end} onChange={(e) => onChange(start, e.target.value)} aria-label="Sampai" />
    </div>
  )
}

export function Select({ value, onChange, options, placeholder, label }: { value: string; onChange: (v: string) => void; options: string[]; placeholder: string; label?: string }) {
  return (
    <select className="input" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label ?? placeholder}>
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {cap(o)}
        </option>
      ))}
    </select>
  )
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
      <span>
        {from}-{Math.min(page * pageSize, total)} dari {total}
      </span>
      <div className="flex items-center gap-1">
        <button type="button" className="btn-secondary px-2 py-1" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Halaman sebelumnya">
          <ChevronLeft className="h-4 w-4" />
        </button>
        <span className="px-2">
          {page} / {pages}
        </span>
        <button type="button" className="btn-secondary px-2 py-1" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Halaman berikutnya">
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Lanjutkan', danger, busy, onConfirm, onCancel }: { open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="card w-full max-w-md p-5">
        <h3 className="text-base font-semibold text-slate-900">{title}</h3>
        <div className="mt-2 text-sm text-slate-600">{message}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={busy}>
            Batal
          </button>
          <button type="button" className={danger ? 'btn-danger' : 'btn-primary'} onClick={onConfirm} disabled={busy}>
            {busy ? 'Memproses...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export function MeterRow({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-center gap-3 py-1.5">
      <span className="truncate text-sm capitalize text-slate-600">{label.replace(/_/g, ' ')}</span>
      <Meter value={value} tone={tone} />
    </div>
  )
}

export function Meter({ value, tone = 'bg-brand-500', label }: { value: number; tone?: string; label?: string }) {
  const v = Math.max(0, Math.min(1, value))
  return (
    <div className="flex items-center gap-2" title={label}>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
        <div className={cx('h-full rounded-full', tone)} style={{ width: `${v * 100}%` }} />
      </div>
      <span className="w-10 text-right text-xs tabular-nums text-slate-500">{(v * 100).toFixed(0)}%</span>
    </div>
  )
}

export function KeyValue({ items }: { items: { k: string; v: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
      {items.map((i) => (
        <div key={i.k} className="min-w-0">
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{i.k}</dt>
          <dd className="mt-0.5 break-words text-sm text-slate-800">{i.v}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Aligned label/value rows: label on the left, value on the right; long values wrap instead of overlapping. */
export function PropertyList({ items }: { items: { k: string; v: ReactNode }[] }) {
  return (
    <dl className="divide-y divide-slate-100">
      {items.map((i) => (
        <div key={i.k} className="grid grid-cols-[9.5rem_minmax(0,1fr)] items-center gap-4 py-2.5 first:pt-0 last:pb-0">
          <dt className="text-sm text-slate-500">{i.k}</dt>
          <dd className="min-w-0 break-words text-sm font-medium text-slate-800">{i.v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Tabs({ tabs, active, onChange }: { tabs: { id: string; label: string }[]; active: string; onChange: (id: string) => void }) {
  return (
    <div className="mb-4 flex gap-1 border-b border-slate-200">
      {tabs.map((t) => (
        <button key={t.id} type="button" onClick={() => onChange(t.id)} className={cx('-mb-px border-b-2 px-3 py-2 text-sm font-medium', active === t.id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:text-slate-700')}>
          {t.label}
        </button>
      ))}
    </div>
  )
}
