import { Loader2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthShell } from '@/components/AuthShell'
import { PasswordInput } from '@/components/PasswordInput'
import { useAuth } from '@/hooks/auth-context'
import { ApiError } from '@/services/api'

type Errors = Partial<Record<'name' | 'email' | 'password' | 'confirm' | 'form', string>>

export default function RegisterPage() {
  const { register } = useAuth()
  const nav = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const err: Errors = {}
    if (name.trim().length < 2) err.name = 'Nama minimal 2 karakter'
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) err.email = 'Format email tidak valid'
    if (password.length < 8) err.password = 'Kata sandi minimal 8 karakter'
    if (confirm !== password) err.confirm = 'Konfirmasi kata sandi tidak sama'
    setErrors(err)
    if (Object.keys(err).length) return
    setBusy(true)
    try {
      await register(name.trim(), email.trim(), password)
      nav('/', { replace: true })
    } catch (ex) {
      if (ex instanceof ApiError && ex.details?.length) {
        const mapped: Errors = {}
        ex.details.forEach((d) => { if (d.field === 'name' || d.field === 'email' || d.field === 'password') mapped[d.field] = d.message })
        setErrors(Object.keys(mapped).length ? mapped : { form: ex.message })
      } else {
        setErrors({ form: ex instanceof Error ? ex.message : 'Pendaftaran gagal' })
      }
    } finally {
      setBusy(false)
    }
  }

  const fieldError = (m?: string) => (m ? <p className="mt-1 text-xs text-red-600">{m}</p> : null)

  return (
    <AuthShell title="Buat akun" subtitle="Daftar untuk mulai menyelidiki insiden." footer={<>Sudah punya akun? <Link to="/login" className="font-medium text-brand-600 hover:underline">Masuk</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {errors.form && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{errors.form}</div>}
        <div>
          <label htmlFor="name" className="label">Nama lengkap</label>
          <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" autoFocus />
          {fieldError(errors.name)}
        </div>
        <div>
          <label htmlFor="email" className="label">Email</label>
          <input id="email" type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
          {fieldError(errors.email)}
        </div>
        <div>
          <label htmlFor="password" className="label">Kata sandi</label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" invalid={!!errors.password} />
          {errors.password ? fieldError(errors.password) : <p className="mt-1 text-xs text-slate-400">Minimal 8 karakter.</p>}
        </div>
        <div>
          <label htmlFor="confirm" className="label">Ulangi kata sandi</label>
          <PasswordInput id="confirm" value={confirm} onChange={setConfirm} autoComplete="new-password" invalid={!!errors.confirm} />
          {fieldError(errors.confirm)}
        </div>
        <button type="submit" className="btn-primary w-full py-2.5" disabled={busy}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" />} {busy ? 'Memproses' : 'Daftar'}
        </button>
      </form>
    </AuthShell>
  )
}
