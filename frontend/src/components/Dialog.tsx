import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { X } from 'lucide-react'

export function Dialog({ title, onClose, children, width = 440 }: { title: string; onClose: () => void; children: ReactNode; width?: number }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return <div className="overlay" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}>
    <section className="dialog" style={{ width: `min(100%, ${width}px)` }} role="dialog" aria-label={title}>
      <header className="dialog-header"><h3>{title}</h3><button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close"><X size={16} /></button></header>
      {children}
    </section>
  </div>
}

export function ConfirmDialog({ title, body, action, onConfirm, onClose }: {
  title: string; body: ReactNode; action: string; onConfirm: () => Promise<void>; onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  return <Dialog title={title} onClose={onClose}>
    <div className="dialog-body">{body}</div>
    <footer className="dialog-footer">
      <button className="btn" onClick={onClose}>Cancel</button>
      <button className="btn btn-danger" disabled={busy} autoFocus onClick={async () => { setBusy(true); try { await onConfirm() } finally { setBusy(false) } }}>{action}</button>
    </footer>
  </Dialog>
}

/** A dialog wrapping a form; `onSubmit` returns an error message to show, or nothing on success. */
export function FormDialog({ title, submitLabel, onSubmit, onClose, children, canSubmit = true }: {
  title: string; submitLabel: string; onSubmit: () => Promise<string | void>; onClose: () => void; children: ReactNode; canSubmit?: boolean
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const problem = await onSubmit()
      if (problem) setError(problem)
    } finally { setBusy(false) }
  }
  return <Dialog title={title} onClose={onClose}>
    <form onSubmit={submit}>
      <div className="dialog-body">{children}{error && <p className="form-error">{error}</p>}</div>
      <footer className="dialog-footer">
        <button type="button" className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={busy || !canSubmit}>{submitLabel}</button>
      </footer>
    </form>
  </Dialog>
}
