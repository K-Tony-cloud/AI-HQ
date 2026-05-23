import { useEffect } from 'react'

export const useKeyboard = ({ onSearch, onRefresh, onClear }) => {
  useEffect(() => {
    const handler = (e) => {
      const active = document.activeElement
      const inInput = active && (
        active.tagName === 'INPUT' ||
        active.tagName === 'TEXTAREA' ||
        active.tagName === 'SELECT'
      )

      // / — focus search (only when not in an input)
      if (e.key === '/' && !inInput) {
        e.preventDefault()
        onSearch?.()
      }
      // F5 or Ctrl+R / Cmd+R — refetch
      if (e.key === 'F5' || (e.ctrlKey && e.key === 'r') || (e.metaKey && e.key === 'r')) {
        e.preventDefault()
        onRefresh?.()
      }
      // Escape — clear search
      if (e.key === 'Escape' && inInput) {
        onClear?.()
        active.blur()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onSearch, onRefresh, onClear])
}
