/**
 * sheetsAdapter.js — Google Apps Script Web App adapter
 *
 * Configured via environment variables:
 *   VITE_SHEETS_URL  — deployed Apps Script URL (ends with /exec)
 */

const SCRIPT_URL = import.meta.env.VITE_SHEETS_URL || ''

function assertUrl() {
  if (!SCRIPT_URL) throw new Error('VITE_SHEETS_URL is not configured. Add it to .env.local.')
}

async function sheetsGet(action, params = {}) {
  assertUrl()
  const url = new URL(SCRIPT_URL)
  url.searchParams.set('action', action)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  const res = await fetch(url.toString())
  const json = await res.json()
  if (!json.ok) throw new Error(json.error || 'Sheets GET error')
  return json.data
}

async function sheetsPost(action, payload = {}) {
  assertUrl()
  const res = await fetch(SCRIPT_URL, {
    method: 'POST',
    body: JSON.stringify({ action, ...payload }),
  })
  const json = await res.json()
  if (!json.ok) throw new Error(json.error || 'Sheets POST error')
  return json.data
}

/* ── Events ──────────────────────────────────────────────────── */

export const getEvents = (date) =>
  sheetsGet('getEvents', date ? { date } : {})

export const getMeta = () =>
  sheetsGet('getMeta')

export const addEvent = (data) =>
  sheetsPost('addEvent', { data })

export const patchEvent = (id, data) =>
  sheetsPost('updateEvent', { id, data })

/* ── Logs ────────────────────────────────────────────────────── */

export const getLogs = (eventId) =>
  sheetsGet('getLogs', { eventId })

export const addLog = (data) =>
  sheetsPost('addLog', { data })
