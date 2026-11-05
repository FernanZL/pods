import { createContext, useContext } from 'react'

export interface ToastAction {
  label: string
  to: string
}

export interface ToastInput {
  message: string
  action?: ToastAction
}

export interface ToastContextValue {
  pushToast: (toast: ToastInput) => void
}

export const ToastContext = createContext<ToastContextValue>({
  pushToast: () => {},
})

export function useToast(): ToastContextValue {
  return useContext(ToastContext)
}
