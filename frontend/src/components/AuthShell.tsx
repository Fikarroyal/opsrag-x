import { Bot, FileSearch, ShieldCheck, Workflow } from 'lucide-react'
import type { ReactNode } from 'react'

const POINTS = [
  { icon: Workflow, title: 'Investigasi bertahap', text: 'Klasifikasi, SOP, riwayat insiden, topologi, diagnostik, dan korelasi log dalam satu alur.' },
  { icon: FileSearch, title: 'Berbasis evidence', text: 'Setiap kesimpulan menyertakan bukti, skor kepercayaan, dan jejak audit.' },
  { icon: ShieldCheck, title: 'Hanya baca', text: 'Tool diagnostik tidak mengubah sistem apa pun. Rekomendasi tetap diverifikasi IT Support.' },
]

/** Two-panel layout shared by the sign-in and registration pages. */
export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-ink-900 p-10 text-slate-300 lg:flex">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand-600/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-brand-500/10 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-600 text-white"><Bot className="h-6 w-6" /></div>
          <div>
            <div className="text-lg font-semibold text-white">OpsRAG-X</div>
            <div className="text-xs text-slate-400">Incident Investigation Agent</div>
          </div>
        </div>
        <div className="relative max-w-md">
          <h2 className="text-3xl font-semibold leading-tight text-white">Temukan akar masalah infrastruktur TI rumah sakit dengan bukti yang jelas.</h2>
          <ul className="mt-8 space-y-5">
            {POINTS.map((p) => (
              <li key={p.title} className="flex gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white/10 text-brand-100"><p.icon className="h-4 w-4" /></div>
                <div>
                  <div className="text-sm font-medium text-white">{p.title}</div>
                  <div className="text-sm text-slate-400">{p.text}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
        <div className="relative text-xs text-slate-500">RS Yogyakarta · IT Operations</div>
      </aside>
      <main className="flex items-center justify-center bg-slate-50 px-5 py-10">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-2 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-600 text-white"><Bot className="h-5 w-5" /></div>
            <span className="text-lg font-semibold text-slate-900">OpsRAG-X</span>
          </div>
          <div className="rounded-xl border border-slate-200 bg-white p-7 shadow-sm">
            <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
            <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
            <div className="mt-6">{children}</div>
          </div>
          <p className="mt-5 text-center text-sm text-slate-500">{footer}</p>
        </div>
      </main>
    </div>
  )
}
