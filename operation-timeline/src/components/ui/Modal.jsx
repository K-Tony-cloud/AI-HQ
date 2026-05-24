import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'

const FOCUSABLE = [
  'button:not([disabled])',
  '[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export const Modal = ({ onClose, children, maxWidth = 'max-w-lg' }) => {
  const panelRef = useRef(null)

  // Lock body scroll
  useEffect(() => {
    const original = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = original }
  }, [])

  // ESC key — capture phase so it fires even if inner elements stop propagation
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler, true)
    return () => document.removeEventListener('keydown', handler, true)
  }, [onClose])

  // Focus first focusable element on mount
  useEffect(() => {
    const el = panelRef.current?.querySelector(FOCUSABLE)
    el?.focus()
  }, [])

  // Trap Tab/Shift+Tab inside the panel
  useEffect(() => {
    const handler = (e) => {
      if (e.key !== 'Tab' || !panelRef.current) return
      const nodes = [...panelRef.current.querySelectorAll(FOCUSABLE)]
      if (!nodes.length) return
      const first = nodes[0]
      const last  = nodes[nodes.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus() }
      } else {
        if (document.activeElement === last)  { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6">
      {/* Backdrop — pointer-events block everything behind the modal */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
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
