export class ApiError extends Error {
  status: number
  code: string
  requestId?: string
  details?: { field: string; message: string }[]
  constructor(status: number, code: string, message: string, requestId?: string, details?: { field: string; message: string }[]) {
    super(message)
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

export const UNAUTHORIZED_EVENT = 'opsragx:unauthorized'

const BASE = import.meta.env.VITE_API_BASE ?? ''

type Params = Record<string, string | number | boolean | undefined | null>

export function qs(params?: Params): string {
  if (!params) return ''
  const u = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') u.set(k, String(v))
  })
  const s = u.toString()
  return s ? `?${s}` : ''
}

export async function api<T>(path: string, init?: RequestInit & { params?: Params }): Promise<T> {
  const { params, ...rest } = init ?? {}
  let res: Response
  try {
    res = await fetch(`${BASE}${path}${qs(params)}`, { headers: { 'Content-Type': 'application/json' }, ...rest })
  } catch {
    throw new ApiError(0, 'network_error', 'Tidak dapat terhubung ke backend. Periksa apakah layanan API berjalan.')
  }
  if (!res.ok) {
    let body: { error?: string; message?: string; request_id?: string; details?: { field: string; message: string }[] } = {}
    try {
      body = await res.json()
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && !path.startsWith('/api/auth/')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(res.status, body.error ?? 'http_error', body.message ?? `Permintaan gagal (${res.status})`, body.request_id, body.details)
  }
  if (res.status === 204) return null as T
  return (await res.json()) as T
}

export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
export const downloadUrl = (path: string) => `${BASE}${path}`
