import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'

/**
 * Portal-based modal shell.
 * - Renders into document.body (escapes all stacking contexts)
 * - Locks body scroll while open
 * - ESC key calls onClose
 * - Clicking backdrop calls onClose
 */
export const Modal = ({ onClose, children, maxWidth = 'max-w-lg' }) => {
  // Lock body scroll
  useEffect(() => {
    const original = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = original }
  }, [])

  // ESC key — use capture so it fires even if inner elements stop propagation
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [onClose])

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6">
      {/* Backdrop — blocks all clicks behind the modal */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel — click does not bubble to backdrop */}
      <div
        className={clsx(
          'relative w-full bg-ops-card border border-ops-border rounded-2xl shadow-2xl',
          'animate-slide-down max-h-[90vh] flex flex-col overflow-hidden',
          maxWidth,
        )}
        role="dialog"
        aria-modal="true"
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>,
    document.body,
  )
}

/** Standardised close button used by all modals */
export const ModalClose = ({ onClose }) => (
  <button
    type="button"
    onClick={onClose}
    aria-label="ปิด"
    className="w-8 h-8 rounded-lg bg-ops-surface border border-ops-border/40 flex items-center justify-center text-ops-text-muted hover:text-ops-danger hover:bg-ops-danger-light transition-colors flex-shrink-0"
  >
    ✕
  </button>
)
