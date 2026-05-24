import { createContext, useContext, useState, useCallback } from 'react'

const ModalContext = createContext(null)

export const ModalProvider = ({ children }) => {
  const [activeModal, setActiveModal] = useState(null) // { type: string, props: object }

  const openModal = useCallback((type, props = {}) => {
    setActiveModal({ type, props })
  }, [])

  const closeModal = useCallback(() => {
    setActiveModal(null)
  }, [])

  return (
    <ModalContext.Provider value={{ activeModal, openModal, closeModal }}>
      {children}
    </ModalContext.Provider>
  )
}

export const useModal = () => {
  const ctx = useContext(ModalContext)
  if (!ctx) throw new Error('useModal must be used within ModalProvider')
  return ctx
}
