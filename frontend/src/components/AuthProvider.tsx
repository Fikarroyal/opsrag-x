import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthContext, useAuth, type AuthApi } from '@/hooks/auth-context'
import { endpoints } from '@/services/endpoints'
import { ApiError, UNAUTHORIZED_EVENT } from '@/services/api'
import type { AuthUser } from '@/types/api'

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    endpoints
      .me()
      .then((u) => active && setUser(u))
      .catch((e: unknown) => {
        if (!(e instanceof ApiError && e.status === 401)) console.error(e)
      })
      .finally(() => active && setLoading(false))
    const onUnauthorized = () => {
      setUser(null)
      qc.clear()
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => {
      active = false
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    }
  }, [qc])

  const login = useCallback(async (email: string, password: string) => {
    qc.clear()
    setUser(await endpoints.login({ email, password }))
  }, [qc])
  const register = useCallback(async (name: string, email: string, password: string) => {
    qc.clear()
    setUser(await endpoints.register({ name, email, password }))
  }, [qc])
  const logout = useCallback(async () => {
    try {
      await endpoints.logout()
    } finally {
      setUser(null)
      qc.clear()
    }
  }, [qc])

  const value = useMemo<AuthApi>(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/** Layout route: renders children only for a signed-in user, otherwise redirects to /login (remembering the target). */
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Memuat sesi...</div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Outlet />
}

/** Login/register routes: signed-in users go straight to the app. */
export function GuestOnly() {
  const { user, loading } = useAuth()
  if (loading) return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Memuat sesi...</div>
  if (user) return <Navigate to="/" replace />
  return <Outlet />
}
