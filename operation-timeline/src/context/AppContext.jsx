import { createContext, useContext, useState, useCallback } from 'react'
import { MOCK_EVENTS, OPERATION_META } from '../data/mockEvents'

const AppContext = createContext(null)

export const AppProvider = ({ children }) => {
  const [events, setEvents] = useState(MOCK_EVENTS)
  const [isAdminMode, setIsAdminMode] = useState(false)
  const [expandedEvents, setExpandedEvents] = useState(new Set(['EVT-013']))
  const [selectedEvent, setSelectedEvent] = useState(null)
  const [densityMode, setDensityMode] = useState('normal') // 'compact' | 'normal'

  const toggleEventExpand = useCallback((eventId) => {
    setExpandedEvents(prev => {
      const next = new Set(prev)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }, [])

  const isEventExpanded = useCallback((eventId) => expandedEvents.has(eventId), [expandedEvents])

  const addEvent = useCallback((event) => {
    setEvents(prev => {
      const newEvent = { ...event, id: `EVT-${Date.now()}` }
      return [...prev, newEvent].sort((a, b) => a.planned_time.localeCompare(b.planned_time))
    })
  }, [])

  const updateEvent = useCallback((eventId, updates) => {
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, ...updates } : e))
  }, [])

  return (
    <AppContext.Provider value={{
      events,
      operationMeta: OPERATION_META,
      isAdminMode, setIsAdminMode,
      expandedEvents,
      toggleEventExpand,
      isEventExpanded,
      selectedEvent, setSelectedEvent,
      densityMode, setDensityMode,
      addEvent,
      updateEvent,
    }}>
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
