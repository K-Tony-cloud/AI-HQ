/**
 * sheetsAdapter.js — Google Apps Script Web App adapter
 */

const SCRIPT_URL = import.meta.env.VITE_SHEETS_URL || ''

let _authToken = ''
export const setAuthToken = (t) => { _authToken = t }
export const getAuthToken = () => _authToken

function assertUrl() {
  if (!SCRIPT_URL) throw new Error('VITE_SHEETS_URL is not configured. Add it to .env.local.')
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

async function fetchWithRetry(url, opts = {}, maxAttempts = 3) {
  const delays = [0, 1000, 2000]
  let lastError
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (delays[attempt] > 0) await sleep(delays[attempt])
    try {
      const res = await fetch(url, opts)
      if (res.status >= 400 && res.status < 500) throw new Error(`HTTP ${res.status}`)
      return res
    } catch (err) {
      lastError = err
      if (err.message && /^HTTP 4/.test(err.message)) throw err
    }
  }
  throw lastError
}

async function sheetsGet(action, params = {}) {
  assertUrl()
  const url = new URL(SCRIPT_URL)
  url.searchParams.set('action', action)
  if (_authToken) url.searchParams.set('token', _authToken)
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
  const res = await fetchWithRetry(url.toString())
  const json = await res.json()
  if (!json.ok) throw new Error(json.error || 'Sheets GET error')
  return json.data
}

async function sheetsPost(action, payload = {}) {
  assertUrl()
  const body = { action, ...payload }
  if (_authToken) body.token = _authToken
  const res = await fetchWithRetry(SCRIPT_URL, {
    method: 'POST',
    body: JSON.stringify(body),
  })
  const json = await res.json()
  if (!json.ok) throw new Error(json.error || 'Sheets POST error')
  return json.data
}

/* ── Health check ─────────────────────────────────────────────── */

export const ping = () => sheetsGet('ping')

/* ── Operations ───────────────────────────────────────────────── */

export const getOperations = () =>
  sheetsGet('getOperations')

export const getOperation = (id) =>
  sheetsGet('getOperation', { id })

export const addOperation = (data) =>
  sheetsPost('addOperation', { data })

export const patchOperation = (id, data) =>
  sheetsPost('updateOperation', { id, data })

export const cloneOperation = (sourceId, newData) =>
  sheetsPost('cloneOperation', { sourceId, data: newData })

export const importOperation = (operation, events) =>
  sheetsPost('importOperation', { data: { operation, events } })

/* ── Events ───────────────────────────────────────────────────── */

export const getEvents = (operationId) =>
  sheetsGet('getEvents', operationId ? { operationId } : {})

export const getMeta = () =>
  sheetsGet('getMeta')

export const addEvent = (data) =>
  sheetsPost('addEvent', { data })

export const patchEvent = (id, data) =>
  sheetsPost('updateEvent', { id, data })

/* ── Logs ─────────────────────────────────────────────────────── */

export const getLogs = (eventId) =>
  sheetsGet('getLogs', { eventId })

export const addLog = (data) =>
  sheetsPost('addLog', { data })

export const getAllLogs = (limit = 50) =>
  sheetsGet('getAllLogs', { limit })

/* ── Attachments ──────────────────────────────────────────────── */

export const getAttachments = (eventId) =>
  sheetsGet('getAttachments', { eventId })

export const uploadAttachment = (data) =>
  sheetsPost('uploadAttachment', { data })

// No-retry upload with 60 s timeout — avoids re-sending large payloads on transient errors
export async function uploadFile(data) {
  assertUrl()
  const controller = new AbortController()
  const tid = setTimeout(() => controller.abort(), 60_000)
  try {
    const res = await fetch(SCRIPT_URL, {
      method: 'POST',
      body: JSON.stringify({ action: 'uploadAttachment', data }),
      signal: controller.signal,
    })
    const json = await res.json()
    if (!json.ok) throw new Error(json.error || 'Upload failed')
    return json.data
  } catch (ex) {
    if (ex.name === 'AbortError') throw new Error('Upload timeout — ไฟล์ใหญ่เกินไปหรือการเชื่อมต่อช้า')
    throw ex
  } finally {
    clearTimeout(tid)
  }
}

export async function testDriveAccess() {
  try {
    return await sheetsGet('testDrive')
  } catch {
    return { driveOk: false, reason: 'network' }
  }
}

/* ── Auth ─────────────────────────────────────────────────────── */

export const loginPin = (pin) =>
  sheetsPost('loginPin', { pin })

export const logoutUser = (token) =>
  sheetsPost('logout', { token })

/* ── Soft delete / restore ────────────────────────────────────── */

export const deleteEvent = (id) =>
  sheetsPost('deleteEvent', { id })

export const restoreEvent = (id) =>
  sheetsPost('restoreEvent', { id })

export const getDeletedEvents = () =>
  sheetsGet('getDeletedEvents')

/* ── User management ─────────────────────────────────────────── */

export const listUsers = () =>
  sheetsGet('listUsers')

export const addUser = (data) =>
  sheetsPost('addUser', { data })

export const removeUser = (id) =>
  sheetsPost('removeUser', { id })
