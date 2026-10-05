import { Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/AuthShell'
import { PasswordInput } from '@/components/PasswordInput'
import { useAuth } from '@/hooks/auth-context'

export default function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const from = (useLocation().state as { from?: string } | null)?.from ?? '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Email dan kata sandi wajib diisi')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      nav(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Gagal masuk')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthShell title="Masuk" subtitle="Masuk untuk membuka dashboard investigasi insiden." footer={<>Belum punya akun? <Link to="/register" className="font-medium text-brand-600 hover:underline">Daftar</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        <div>
          <label htmlFor="email" className="label">Email</label>
          <input id="email" type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" autoFocus />
        </div>
        <div>
          <label htmlFor="password" className="label">Kata sandi</label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
        </div>
        <button type="submit" className="btn-primary w-full py-2.5" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} {busy ? 'Memproses' : 'Masuk'}
        </button>
      </form>
    </AuthShell>
  )
}
