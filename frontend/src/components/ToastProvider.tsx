import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { IconClose } from './Icons'
import { ToastContext, type ToastInput } from './ToastContext'

interface ToastEntry extends ToastInput {
  id: number
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastEntry[]>([])
  const nextIdRef = useRef(1)

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((item) => item.id !== id))
  }, [])

  const pushToast = useCallback(
    (toast: ToastInput) => {
      const id = nextIdRef.current++
      setItems((prev) => [...prev.slice(-2), { ...toast, id }])
      window.setTimeout(() => {
        dismiss(id)
      }, 6500)
    },
    [dismiss],
  )

  const value = useMemo(() => ({ pushToast }), [pushToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      {items.length > 0 ? (
        <div className="toast-region" role="status" aria-live="polite">
          {items.map((item) => (
            <div key={item.id} className="toast-item">
              <div className="toast-item-body">
                <span>{item.message}</span>
                {item.action ? (
                  <Link
                    to={item.action.to}
                    className="toast-link"
                    onClick={() => dismiss(item.id)}
                  >
                    {item.action.label}
                  </Link>
                ) : null}
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => dismiss(item.id)}
                aria-label="Dismiss notification"
              >
                <IconClose size={13} />
              </button>
            </div>
          ))}
        </div>
      ) : null}
    </ToastContext.Provider>
  )
}
