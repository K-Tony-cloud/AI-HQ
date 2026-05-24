import { createContext, useContext, useState, useCallback, useRef } from 'react'

// Split into two contexts so action-only consumers (EventCard, Header, etc.)
// don't re-render when activeModal changes.
const ModalStateContext   = createContext(null)
const ModalActionsContext = createContext(null)

export const ModalProvider = ({ children }) => {
  const [activeModal, setActiveModal] = useState(null) // { type, props } | null
  const lastFocusRef = useRef(null)

  const openModal = useCallback((type, props = {}) => {
    lastFocusRef.current = document.activeElement
    setActiveModal({ type, props })
  }, [])

  const closeModal = useCallback(() => {
    setActiveModal(null)
    // Restore focus to whichever element triggered the modal open,
    // deferred by one frame so inert is removed before we try to focus.
    requestAnimationFrame(() => {
      lastFocusRef.current?.focus()
      lastFocusRef.current = null
    })
  }, [])

  return (
    <ModalActionsContext.Provider value={{ openModal, closeModal }}>
      <ModalStateContext.Provider value={{ activeModal }}>
        {children}
      </ModalStateContext.Provider>
    </ModalActionsContext.Provider>
  )
}

// Full hook — use only when you need both state and actions (ModalHost, AppContent).
export const useModal = () => {
  const state   = useContext(ModalStateContext)
  const actions = useContext(ModalActionsContext)
  if (!state || !actions) throw new Error('useModal must be used within ModalProvider')
  return { ...state, ...actions }
}

// Actions-only hook — use in components that trigger modals but never read activeModal.
// These components will NOT re-render when a modal opens or closes.
export const useModalActions = () => {
  const ctx = useContext(ModalActionsContext)
  if (!ctx) throw new Error('useModalActions must be used within ModalProvider')
  return ctx
}

// State-only hook — use when you only need to read activeModal.
export const useModalState = () => {
  const ctx = useContext(ModalStateContext)
  if (!ctx) throw new Error('useModalState must be used within ModalProvider')
  return ctx
}
