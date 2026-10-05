export const fmtDateTime = (iso?: string | null): string => (iso ? iso.replace('T', ' ').slice(0, 19) : 'n/a')
export const fmtTime = (iso?: string | null): string => (iso ? iso.replace('T', ' ').slice(11, 19) : 'n/a')
export const pct = (v?: number | null, digits = 0): string => (v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(digits)}%`)
export const num = (v?: number | null, digits = 1): string => (v === null || v === undefined ? 'n/a' : v.toFixed(digits))
export const cap = (s?: string | null): string => (s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ') : 'n/a')
export const toLocalInput = (iso?: string | null): string => (iso ? iso.slice(0, 16) : '')

export const SEVERITY_COLOR: Record<string, string> = { low: '#64748b', medium: '#2563eb', high: '#ea580c', critical: '#dc2626' }
export const CHART_COLORS = ['#2563eb', '#0891b2', '#7c3aed', '#ea580c', '#16a34a', '#db2777', '#ca8a04', '#475569']
export const SCENARIO_TIMES: { label: string; value: string }[] = [
  { label: 'S1 Poli 3 (28 Sep 09:47)', value: '2026-09-28T09:47' },
  { label: 'S2 DNS (27 Sep 13:20)', value: '2026-09-27T13:20' },
  { label: 'S3 Database (26 Sep 10:35)', value: '2026-09-26T10:35' },
  { label: 'S4 Overload (25 Sep 14:10)', value: '2026-09-25T14:10' },
  { label: 'S5 Farmasi (24 Sep 08:55)', value: '2026-09-24T08:55' },
]
export const UNITS = ['Poli 1', 'Poli 2', 'Poli 3', 'Farmasi', 'Kasir', 'Laboratorium', 'Radiologi', 'IGD', 'Rekam Medis', 'IT']
export const SERVICES = ['SIMRS', 'SIM-APOTEK', 'DNS', 'DATABASE', 'FILE SERVER', 'MONITORING']
export const CATEGORIES = ['network', 'dns', 'server', 'application', 'database', 'hardware', 'authentication', 'configuration', 'service', 'unknown']
