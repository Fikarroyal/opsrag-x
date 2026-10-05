import { createContext, useContext } from 'react'

export type ToastKind = 'success' | 'error' | 'info'
export interface ToastApi {
  push: (kind: ToastKind, message: string) => void
}
export const ToastContext = createContext<ToastApi>({ push: () => undefined })
export const useToast = (): ToastApi => useContext(ToastContext)
