import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import { MOCK_EVENTS, OPERATION_META } from '../mock/events'
import {
  fetchEvents, fetchMeta,
  createEvent as apiCreateEvent,
  patchEvent  as apiPatchEvent,
  createLog,
  IS_MOCK, POLL_INTERVAL,
} from '../services/eventService'
import { createPoller } from '../services/realtime'
import { useToast } from './ToastContext'
import { useNetworkStatus } from '../hooks/useNetworkStatus'

const AppContext = createContext(null)

export const AppProvider = ({ children }) => {
  /* ── Data state ───────────────────────────────────────────────
     Seed with mock data so Header/Sidebar always have valid props.
     In mock mode: isLoading stays false — no async trip needed.
     In live mode: isLoading = true until first fetch resolves.
  ─────────────────────────────────────────────────────────────── */
  const [events,        setEvents]        = useState(MOCK_EVENTS)
  const [operationMeta, setOperationMeta] = useState(OPERATION_META)
  const [isLoading,     setIsLoading]     = useState(!IS_MOCK)
  const [error,         setError]         = useState(null)
  const [isSyncing,     setIsSyncing]     = useState(false)
  const [lastSyncAt,    setLastSyncAt]    = useState(IS_MOCK ? new Date() : null)

  /* ── UI state ─────────────────────────────────────────────── */
  const [isAdminMode,    setIsAdminMode]    = useState(false)
  const [expandedEvents, setExpandedEvents] = useState(new Set(['EVT-013']))
  const [selectedEvent,  setSelectedEvent]  = useState(null)
  const [densityMode,    setDensityMode]    = useState('normal')

  /* ── Toast ────────────────────────────────────────────────── */
  const { addToast } = useToast()

  /* ── Network status ───────────────────────────────────────── */
  const isOnline = useNetworkStatus()
  const isOnlineRef      = useRef(navigator.onLine)
  const networkInitRef   = useRef(false)

  /* ── Events ref (for optimistic rollback) ─────────────────── */
  const eventsRef = useRef(MOCK_EVENTS)

  /* ── Snapshot recorder ────────────────────────────────────── */
  const snapshotsRef = useRef([])

  /* ── Previous events ref for change detection ─────────────── */
  const prevEventsRef  = useRef(null)
  const isInitialLoad  = useRef(true)

  /* ── Fetch from backend ───────────────────────────────────── */
  const loadAll = useCallback(async (silent = false) => {
    if (!silent) setIsLoading(true)
    else         setIsSyncing(true)
    setError(null)
    try {
      const [evts, meta] = await Promise.all([fetchEvents(), fetchMeta()])
      setEvents(evts)
      if (meta) setOperationMeta(meta)
      setLastSyncAt(new Date())
    } catch (ex) {
      setError(ex.message || 'โหลดข้อมูลไม่สำเร็จ')
    } finally {
      setIsLoading(false)
      setIsSyncing(false)
    }
  }, [])

  /* ── Initial load (live mode only) ───────────────────────── */
  useEffect(() => {
    if (!IS_MOCK) loadAll()
  }, [loadAll])

  /* ── Realtime polling (live mode only) ────────────────────── */
  const pollerRef = useRef(null)
  useEffect(() => {
    if (IS_MOCK) return
    const poller = createPoller(() => fetchEvents(), POLL_INTERVAL)
    const unsub  = poller.subscribe(({ data, error: pollErr }) => {
      if (data) {
        setEvents(prev => {
          // Change detection — only after initial load
          if (!isInitialLoad.current && prevEventsRef.current) {
            const prevMap = new Map(prevEventsRef.current.map(e => [e.id, e]))
            data.forEach(ev => {
              const old = prevMap.get(ev.id)
              if (old && old.status !== ev.status) {
                const type = ev.status === 'completed' ? 'success' : 'info'
                addToast(`${ev.id}: เปลี่ยนสถานะเป็น ${ev.status}`, type)
              }
            })
          }
          isInitialLoad.current = false
          prevEventsRef.current = data
          return data
        })
        setLastSyncAt(new Date())
      }
      if (pollErr) setError(pollErr)
    })
    poller.start()
    pollerRef.current = poller
    return () => { poller.stop(); unsub() }
  }, [addToast])

  /* ── Keep isOnlineRef and eventsRef in sync ──────────────── */
  useEffect(() => { isOnlineRef.current = isOnline }, [isOnline])
  useEffect(() => { eventsRef.current = events }, [events])

  /* ── Snapshot recorder (live only) ───────────────────────── */
  useEffect(() => {
    if (IS_MOCK || events.length === 0) return
    const snap = { ts: Date.now(), events: events }
    snapshotsRef.current = [...snapshotsRef.current.slice(-119), snap]
  }, [events])

  /* ── Pause/resume polling on network change ──────────────── */
  useEffect(() => {
    if (IS_MOCK || !pollerRef.current) return
    if (!networkInitRef.current) { networkInitRef.current = true; return }
    if (isOnline) {
      if (!document.hidden) {
        pollerRef.current.start()
        pollerRef.current.refresh()
      }
      addToast('กลับมาออนไลน์แล้ว', 'success')
    } else {
      pollerRef.current.stop()
      addToast('ขาดการเชื่อมต่ออินเทอร์เน็ต', 'warning')
    }
  }, [isOnline, addToast])

  /* ── Pause/resume polling on tab visibility change ───────── */
  useEffect(() => {
    if (IS_MOCK) return
    const handleVisibility = () => {
      if (!pollerRef.current) return
      if (document.hidden) {
        pollerRef.current.stop()
      } else if (isOnlineRef.current) {
        pollerRef.current.start()
        pollerRef.current.refresh()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  /* ── Event CRUD ───────────────────────────────────────────── */
  const addEvent = useCallback(async (eventData) => {
    const newEvent = await apiCreateEvent(eventData)
    setEvents(prev =>
      [...prev, newEvent].sort((a, b) => a.planned_time.localeCompare(b.planned_time))
    )
    return newEvent
  }, [])

  const buildAuditMessage = (updates) => {
    if (updates.status) return `เปลี่ยนสถานะเป็น: ${updates.status}`
    return 'แก้ไขข้อมูลเหตุการณ์'
  }

  const updateEvent = useCallback(async (eventId, updates) => {
    const snapshot = eventsRef.current
    // Optimistic update
    setEvents(prev => prev.map(e => e.id === eventId ? { ...e, ...updates } : e))
    try {
      await apiPatchEvent(eventId, updates)
      if (!IS_MOCK) {
        try {
          await createLog({
            event_id: eventId,
            time:     new Date().toTimeString().slice(0, 5),
            message:  buildAuditMessage(updates),
            user:     'ADMIN',
            type:     'update',
          })
        } catch (_) {}
      }
    } catch (err) {
      // Rollback
      setEvents(snapshot)
      addToast('บันทึกไม่สำเร็จ — ข้อมูลถูกยกเลิก', 'error')
      throw err
    }
  }, [addToast])

  /* ── Expand/collapse ──────────────────────────────────────── */
  const toggleEventExpand = useCallback((eventId) => {
    setExpandedEvents(prev => {
      const next = new Set(prev)
      if (next.has(eventId)) next.delete(eventId)
      else next.add(eventId)
      return next
    })
  }, [])

  const isEventExpanded = useCallback(
    (eventId) => expandedEvents.has(eventId),
    [expandedEvents],
  )

  return (
    <AppContext.Provider value={{
      events,
      operationMeta,
      isLoading,
      error,
      isSyncing,
      lastSyncAt,
      refetch:     () => loadAll(false),
      isAdminMode, setIsAdminMode,
      expandedEvents,
      toggleEventExpand,
      isEventExpanded,
      selectedEvent, setSelectedEvent,
      addEvent,
      updateEvent,
      densityMode, setDensityMode,
      isMockMode: IS_MOCK,
      getSnapshots: () => snapshotsRef.current,
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
