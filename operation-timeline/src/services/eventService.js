import { MOCK_EVENTS, OPERATION_META } from '../mock/events'
import { getLogsForEvent as mockGetLogs } from '../mock/logs'
import { apiFetch } from './api'

// Switch to 'live' to hit the real API (set VITE_API_MODE=live in .env.local)
const USE_MOCK = import.meta.env.VITE_API_MODE !== 'live'

export const fetchEvents = async () => {
  if (USE_MOCK) return MOCK_EVENTS
  return apiFetch('/events')
}

export const fetchMeta = async () => {
  if (USE_MOCK) return OPERATION_META
  return apiFetch('/meta')
}

export const fetchLogs = (eventId) => {
  if (USE_MOCK) return mockGetLogs(eventId)
  // TODO: wire to apiFetch('/logs/' + eventId) when backend is ready
  return []
}

export const postEventUpdate = async (eventId, updates) => {
  if (USE_MOCK) return { ok: true }
  return apiFetch(`/events/${eventId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
}
