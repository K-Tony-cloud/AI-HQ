/**
 * eventService.js — unified data access layer
 *
 * VITE_API_MODE=mock (default) → local mock data
 * VITE_API_MODE=live           → Google Sheets via sheetsAdapter
 */

import { MOCK_OPERATIONS, MOCK_EVENTS, getEventsForOperation } from '../mock/events'
import { getLogsForEvent as mockGetLogs, MOCK_LOGS } from '../mock/logs'
import * as sheets from './sheetsAdapter'

const USE_MOCK = import.meta.env.VITE_API_MODE !== 'live'

/* ── Operations ──────────────────────────────────────────────── */

export const fetchOperations = async () => {
  if (USE_MOCK) return MOCK_OPERATIONS
  return sheets.getOperations()
}

export const fetchOperation = async (id) => {
  if (USE_MOCK) return MOCK_OPERATIONS.find(o => o.id === id) || null
  return sheets.getOperation(id)
}

export const createOperation = async (data) => {
  const newOp = {
    ...data,
    id:         `OP-${Date.now()}`,
    status:     data.status || 'ACTIVE',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
  if (USE_MOCK) return newOp
  return sheets.addOperation(newOp)
}

export const patchOperation = async (id, updates) => {
  if (USE_MOCK) return { ok: true }
  return sheets.patchOperation(id, updates)
}

export const duplicateOperation = async (sourceId, newData) => {
  if (USE_MOCK) {
    const source = MOCK_OPERATIONS.find(o => o.id === sourceId)
    if (!source) throw new Error('Source operation not found')
    return { ...source, ...newData, id: `OP-${Date.now()}`, status: 'ACTIVE' }
  }
  return sheets.cloneOperation(sourceId, newData)
}

/* ── Events ──────────────────────────────────────────────────── */

export const fetchEvents = async (operationId) => {
  if (USE_MOCK) {
    if (operationId) return getEventsForOperation(operationId)
    return MOCK_EVENTS
  }
  return sheets.getEvents(operationId)
}

export const fetchMeta = async () => {
  if (USE_MOCK) return MOCK_OPERATIONS[0]
  return sheets.getMeta()
}

export const fetchLogs = async (eventId) => {
  if (USE_MOCK) return mockGetLogs(eventId)
  return sheets.getLogs(eventId)
}

/* ── Event CRUD ──────────────────────────────────────────────── */

export const createEvent = async (data) => {
  const newEvent = {
    ...data,
    id:          `EVT-${Date.now()}`,
    actual_time:  data.actual_time  || null,
    end_time:     data.end_time     || null,
    status:      data.status      || 'upcoming',
    duration:    data.duration    || 30,
  }
  if (USE_MOCK) return newEvent
  return sheets.addEvent(newEvent)
}

export const patchEvent = async (id, updates) => {
  if (USE_MOCK) return { ok: true }
  return sheets.patchEvent(id, updates)
}

export const createLog = async (data) => {
  if (USE_MOCK) return data
  return sheets.addLog(data)
}

export const fetchAllLogs = (limit = 50) =>
  USE_MOCK
    ? Promise.resolve(Object.values(MOCK_LOGS).flat().slice(0, limit))
    : sheets.getAllLogs(limit)

/* ── Connection test ─────────────────────────────────────────── */

export const testConnection = async () => {
  if (USE_MOCK) return { ok: true, mode: 'mock', events: 0, logs: 0 }
  const data = await sheets.ping()
  return { ok: true, mode: 'live', ...data }
}

/* ── Meta ────────────────────────────────────────────────────── */

export const IS_MOCK = USE_MOCK
export const POLL_INTERVAL = parseInt(import.meta.env.VITE_POLL_INTERVAL || '30000', 10)
