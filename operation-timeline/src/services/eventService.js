/**
 * eventService.js — unified data access layer
 *
 * Reads VITE_API_MODE from environment:
 *   'mock' (default) — returns local mock data synchronously
 *   'live'           — calls Google Sheets via sheetsAdapter
 *
 * All exported functions are async to allow transparent switching.
 */

import { MOCK_EVENTS, OPERATION_META } from '../mock/events'
import { getLogsForEvent as mockGetLogs, MOCK_LOGS } from '../mock/logs'
import * as sheets from './sheetsAdapter'

const USE_MOCK = import.meta.env.VITE_API_MODE !== 'live'

/* ── Read ────────────────────────────────────────────────────── */

export const fetchEvents = async (date) => {
  if (USE_MOCK) {
    if (date) return MOCK_EVENTS.filter(e => e.date === date)
    return MOCK_EVENTS
  }
  return sheets.getEvents(date)
}

export const fetchMeta = async () => {
  if (USE_MOCK) return OPERATION_META
  return sheets.getMeta()
}

export const fetchLogs = async (eventId) => {
  if (USE_MOCK) return mockGetLogs(eventId)
  return sheets.getLogs(eventId)
}

/* ── Write ───────────────────────────────────────────────────── */

export const createEvent = async (data) => {
  const newEvent = {
    ...data,
    id:         `EVT-${Date.now()}`,
    date:       data.date       || '2026-05-22',
    actual_time: data.actual_time || null,
    end_time:    data.end_time    || null,
    status:     data.status     || 'upcoming',
    duration:   data.duration   || 30,
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
