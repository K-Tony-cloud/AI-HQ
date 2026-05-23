import { useEffect } from 'react'
import { useToast } from '../../context/ToastContext'
import clsx from 'clsx'

const TYPE_STYLES = {
  success: 'bg-ops-success-light border border-ops-success/40 text-ops-success',
  error:   'bg-ops-danger-light  border border-ops-danger/40  text-ops-danger',
  warning: 'bg-ops-warning-light border border-ops-warning/40 text-ops-warning',
  info:    'bg-ops-info-light    border border-ops-info/40    text-ops-info',
}

const TYPE_ICONS = {
  success: '✓',
  error:   '✕',
  warning: '⚠',
  info:    'ℹ',
}

const Toast = ({ id, message, type, duration }) => {
  const { removeToast } = useToast()

  useEffect(() => {
    if (!duration) return
    const t = setTimeout(() => removeToast(id), duration)
    return () => clearTimeout(t)
  }, [id, duration, removeToast])

  return (
    <div
      className={clsx(
        'flex items-start gap-2.5 px-3.5 py-2.5 rounded-xl shadow-card-md',
        'animate-slide-in-right min-w-[220px] max-w-xs',
        TYPE_STYLES[type] || TYPE_STYLES.info,
      )}
    >
      <span className="text-sm font-bold flex-shrink-0 mt-0.5">
        {TYPE_ICONS[type] || TYPE_ICONS.info}
      </span>
      <p className="text-xs font-medium flex-1 leading-relaxed">{message}</p>
      <button
        onClick={() => removeToast(id)}
        className="flex-shrink-0 opacity-60 hover:opacity-100 transition-opacity text-xs font-bold ml-1"
        aria-label="ปิด"
      >
        ✕
      </button>
    </div>
  )
}

export const ToastContainer = () => {
  const { toasts } = useToast()

  if (!toasts.length) return null

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2">
      {toasts.map(t => (
        <Toast key={t.id} {...t} />
      ))}
    </div>
  )
}
