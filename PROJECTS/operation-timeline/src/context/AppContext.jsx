import { createContext, useContext, useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { MOCK_OPERATIONS, MOCK_EVENTS, getEventsForOperation } from '../mock/events'
import {
  fetchEvents, fetchOperations,
  createEvent    as apiCreateEvent,
  patchEvent     as apiPatchEvent,
  createOperation as apiCreateOperation,
  patchOperation  as apiPatchOperation,
  duplicateOperation as apiDuplicateOperation,
  importOperationFromCSV as apiImportOperation,
  createLog,
  IS_MOCK, POLL_INTERVAL,
  removeEvent    as apiDeleteEvent,
  undeleteEvent  as apiRestoreEvent,
} from '../services/eventService'
import { createPoller } from '../services/realtime'
import { useToast } from './ToastContext'
import { useNetworkStatus } from '../hooks/useNetworkStatus'
import { useNotifications } from '../hooks/useNotifications'
import { useAuth } from './AuthContext'

const AppContext = createContext(null)

const STORAGE_KEY = 'ops_current_operation_id'

function loadStoredOperationId(operations) {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored && operations.some(o => o.id === stored)) return stored
  } catch (_) {}
  return operations[0]?.id || null
}

export const AppProvider = ({ children }) => {
  /* ── Operations ───────────────────────────────────────────────── */
  const [operations,         setOperations]         = useState(MOCK_OPERATIONS)
  const [currentOperationId, setCurrentOperationId] = useState(
    () => loadStoredOperationId(MOCK_OPERATIONS)
  )

  const operationMeta = useMemo(
    () => operations.find(o => o.id === currentOperationId) || operations[0] || null,
    [operations, currentOperationId],
  )

  /* ── Events ───────────────────────────────────────────────────── */
  const [events,     setEvents]     = useState(() =>
    IS_MOCK ? getEventsForOperation(MOCK_OPERATIONS[0]?.id) : MOCK_EVENTS
  )
  const [isLoading,  setIsLoading]  = useState(!IS_MOCK)
  const [error,      setError]      = useState(null)
  const [isSyncing,  setIsSyncing]  = useState(false)
  const [lastSyncAt, setLastSyncAt] = useState(IS_MOCK ? new Date() : null)

  /* ── Auth ─────────────────────────────────────────────────────── */
  const { isOpAdmin } = useAuth()

  /* ── UI state ─────────────────────────────────────────────────── */
  const [expandedEventId, setExpandedEventId] = useState(null)
  const [selectedEvent,   setSelectedEvent]  = useState(null)
  const [densityMode,    setDensityMode]    = useState('normal')
  const [editingEventId, setEditingEventId] = useState(null)
  const [playbackIndex,  setPlaybackIndex]  = useState(-1)

  /* ── Contexts ─────────────────────────────────────────────────── */
  const { addToast } = useToast()
  const { notify, requestPermission } = useNotifications()
  const isOnline = useNetworkStatus()

  /* ── Refs ─────────────────────────────────────────────────────── */
  const isOnlineRef    = useRef(navigator.onLine)
  const networkInitRef = useRef(false)
  const eventsRef      = useRef(events)
  const snapshotsRef   = useRef([])
  const prevEventsRef  = useRef(null)
  const isInitialLoad  = useRef(true)
  const pollerRef      = useRef(null)

  /* ── Persist current operation to localStorage ────────────────── */
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, currentOperationId) } catch (_) {}
  }, [currentOperationId])

  /* ── Load all data ────────────────────────────────────────────── */
  const loadAll = useCallback(async (silent = false, opId = null) => {
    const targetId = opId || currentOperationId
    if (!silent) setIsLoading(true)
    else         setIsSyncing(true)
    setError(null)
    try {
      const [ops, evts] = await Promise.all([
        fetchOperations(),
        fetchEvents(targetId),
      ])
      setOperations(ops)
      setEvents(evts)
      setLastSyncAt(new Date())
    } catch (ex) {
      setError(ex.message || 'โหลดข้อมูลไม่สำเร็จ')
    } finally {
      setIsLoading(false)
      setIsSyncing(false)
    }
  }, [currentOperationId])

  /* ── Initial load (live mode only) ───────────────────────────── */
  useEffect(() => {
    if (!IS_MOCK) loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Reload events when operation changes (live) ─────────────── */
  useEffect(() => {
    if (!IS_MOCK) {
      isInitialLoad.current = true
      prevEventsRef.current = null
      loadAll(true, currentOperationId)
      // Restart poller for new operation
      if (pollerRef.current) {
        pollerRef.current.stop()
        pollerRef.current = null
      }
    } else {
      // Mock: filter events client-side
      setEvents(getEventsForOperation(currentOperationId))
    }
  }, [currentOperationId]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ── Realtime polling (live mode only) ───────────────────────── */
  useEffect(() => {
    if (IS_MOCK) return
    const opId = currentOperationId
    const poller = createPoller(() => fetchEvents(opId), POLL_INTERVAL)
    const unsub  = poller.subscribe(({ data, error: pollErr }) => {
      if (data) {
        setEvents(prev => {
          const prevHash = prevEventsRef.current
            ? prevEventsRef.current.map(e => `${e.id}:${e.updated_at}:${e.status}`).join(',')
            : null
          const newHash = data.map(e => `${e.id}:${e.updated_at}:${e.status}`).join(',')
          if (prevHash === newHash && !isInitialLoad.current) return prev

          if (!isInitialLoad.current && prevEventsRef.current) {
            const prevMap = new Map(prevEventsRef.current.map(e => [e.id, e]))
            data.forEach(ev => {
              const old = prevMap.get(ev.id)
              if (old && old.status !== ev.status) {
                const type = ev.status === 'completed' ? 'success' : 'info'
                addToast(`${ev.id}: เปลี่ยนสถานะเป็น ${ev.status}`, type)
                notify(`${ev.id}: ${ev.title}`, `สถานะเปลี่ยนเป็น ${ev.status}`, ev.type === 'emergency' || ev.priority === 'critical')
              }
            })
          }

          if (isInitialLoad.current) {
            isInitialLoad.current = false
            requestPermission()
          }

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
  }, [currentOperationId, addToast, notify, requestPermission])

  /* ── Keep refs in sync ────────────────────────────────────────── */
  useEffect(() => { isOnlineRef.current = isOnline }, [isOnline])
  useEffect(() => { eventsRef.current = events }, [events])

  /* ── Snapshot recorder (live only) ───────────────────────────── */
  useEffect(() => {
    if (IS_MOCK || events.length === 0) return
    const snap = { ts: Date.now(), events }
    snapshotsRef.current = [...snapshotsRef.current.slice(-119), snap]
  }, [events])

  /* ── Pause/resume polling on network change ──────────────────── */
  useEffect(() => {
    if (IS_MOCK || !pollerRef.current) return
    if (!networkInitRef.current) { networkInitRef.current = true; return }
    if (isOnline) {
      if (!document.hidden) { pollerRef.current.start(); pollerRef.current.refresh() }
      addToast('กลับมาออนไลน์แล้ว', 'success')
    } else {
      pollerRef.current.stop()
      addToast('ขาดการเชื่อมต่ออินเทอร์เน็ต', 'warning')
    }
  }, [isOnline, addToast])

  /* ── Pause/resume polling on tab visibility ──────────────────── */
  useEffect(() => {
    if (IS_MOCK) return
    const handleVisibility = () => {
      if (!pollerRef.current) return
      if (document.hidden) pollerRef.current.stop()
      else if (isOnlineRef.current) { pollerRef.current.start(); pollerRef.current.refresh() }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [])

  /* ── Operation CRUD ───────────────────────────────────────────── */
  const addOperation = useCallback(async (data) => {
    const newOp = await apiCreateOperation(data)
    setOperations(prev => [newOp, ...prev])
    setCurrentOperationId(newOp.id)
    return newOp
  }, [])

  const updateOperation = useCallback(async (id, updates) => {
    await apiPatchOperation(id, updates)
    setOperations(prev => prev.map(o => o.id === id ? { ...o, ...updates } : o))
  }, [])

  const archiveOperation = useCallback(async (id) => {
    await apiPatchOperation(id, { status: 'ARCHIVED' })
    setOperations(prev => prev.map(o => o.id === id ? { ...o, status: 'ARCHIVED' } : o))
    if (currentOperationId === id) {
      const next = operations.find(o => o.id !== id && o.status !== 'ARCHIVED')
      if (next) setCurrentOperationId(next.id)
    }
  }, [currentOperationId, operations])

  const cloneOperation = useCallback(async (sourceId, newData) => {
    const cloned = await apiDuplicateOperation(sourceId, newData)
    setOperations(prev => [cloned, ...prev])
    setCurrentOperationId(cloned.id)
    return cloned
  }, [])

  const switchOperation = useCallback((id) => {
    setPlaybackIndex(-1)
    snapshotsRef.current = []
    setCurrentOperationId(id)
  }, [])

  const importOperation = useCallback(async (operationData, events) => {
    const result = await apiImportOperation(operationData, events)
    setOperations(prev => [result.operation, ...prev])
    setCurrentOperationId(result.operation.id)
    return result
  }, [])

  /* ── Event CRUD ───────────────────────────────────────────────── */
  const addEvent = useCallback(async (eventData) => {
    const newEvent = await apiCreateEvent({
      ...eventData,
      operation_id: currentOperationId,
      date:         operationMeta?.date || eventData.date,
    })
    setEvents(prev =>
      [...prev, newEvent].sort((a, b) => a.planned_time.localeCompare(b.planned_time))
    )
    return newEvent
  }, [currentOperationId, operationMeta])

  const buildAuditMessage = (updates) => {
    if (updates.status) return `เปลี่ยนสถานะเป็น: ${updates.status}`
    return 'แก้ไขข้อมูลเหตุการณ์'
  }

  const updateEvent = useCallback(async (eventId, updates) => {
    const snapshot = eventsRef.current
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
      setEvents(snapshot)
      addToast('บันทึกไม่สำเร็จ — ข้อมูลถูกยกเลิก', 'error')
      throw err
    }
  }, [addToast])

  const deleteEvent = useCallback(async (eventId) => {
    setEvents(prev => prev.filter(e => e.id !== eventId))
    try {
      await apiDeleteEvent(eventId)
    } catch (err) {
      addToast('ลบไม่สำเร็จ', 'error')
      throw err
    }
  }, [addToast])

  const restoreEvent = useCallback(async (eventId) => {
    try {
      await apiRestoreEvent(eventId)
      addToast('กู้คืนเหตุการณ์แล้ว', 'success')
    } catch (err) {
      addToast('กู้คืนไม่สำเร็จ', 'error')
      throw err
    }
  }, [addToast])

  /* ── Expand/collapse — one at a time ─────────────────────────── */
  const toggleEventExpand = useCallback((eventId) => {
    setExpandedEventId(prev => prev === eventId ? null : eventId)
  }, [])

  const isEventExpanded = useCallback(
    (eventId) => eventId === expandedEventId,
    [expandedEventId],
  )

  /* ── Computed: displayEvents ──────────────────────────────────── */
  const displayEvents = playbackIndex >= 0
    ? (snapshotsRef.current[playbackIndex]?.events ?? events)
    : events

  return (
    <AppContext.Provider value={{
      /* operations */
      operations,
      currentOperationId,
      operationMeta,
      switchOperation,
      addOperation,
      updateOperation,
      archiveOperation,
      cloneOperation,
      importOperation,
      /* events */
      events,
      displayEvents,
      isLoading,
      error,
      isSyncing,
      lastSyncAt,
      refetch:     () => loadAll(false),
      /* ui */
      isAdminMode: isOpAdmin,
      expandedEventId,
      toggleEventExpand,
      isEventExpanded,
      selectedEvent, setSelectedEvent,
      addEvent,
      updateEvent,
      deleteEvent,
      restoreEvent,
      densityMode, setDensityMode,
      isMockMode: IS_MOCK,
      getSnapshots: () => snapshotsRef.current,
      editingEventId, setEditingEventId,
      playbackIndex,  setPlaybackIndex,
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
