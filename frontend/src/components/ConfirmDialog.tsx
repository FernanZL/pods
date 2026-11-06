import { useEffect, useRef, type ReactNode } from 'react'
import { Spinner } from './Spinner'
import './ConfirmDialog.css'

interface ConfirmDialogProps {
  open: boolean
  title: string
  description: string
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onClose: () => void
  children?: ReactNode // extra controls between the description and the buttons
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  danger = true,
  busy = false,
  onConfirm,
  onClose,
  children,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby="confirm-dialog-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === dialogRef.current && !busy) {
          onClose()
        }
      }}
    >
      <div className="confirm-dialog-inner">
        <h2 id="confirm-dialog-title" className="confirm-dialog-title">
          {title}
        </h2>
        <p className="confirm-dialog-desc">{description}</p>
        {children}
        <div className="confirm-dialog-footer">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? <Spinner size={13} label="Working" /> : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </dialog>
  )
}
