/**
 * useEvents — data fetching hook for events with loading/error states.
 *
 * Returns the same shape as AppContext but as a standalone hook
 * for components that need direct access without the full context.
 * In most cases, prefer useApp() from AppContext.
 */

import { useState, useEffect, useCallback } from 'react'
import { fetchEvents } from '../services/eventService'

export const useEvents = (date) => {
  const [events,    setEvents]    = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error,     setError]     = useState(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await fetchEvents(date)
      setEvents(data)
    } catch (ex) {
      setError(ex.message || 'โหลดข้อมูลไม่สำเร็จ')
    } finally {
      setIsLoading(false)
    }
  }, [date])

  useEffect(() => { load() }, [load])

  return { events, isLoading, error, refetch: load }
}
