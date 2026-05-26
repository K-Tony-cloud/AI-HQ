/**
 * Events.gs — CRUD operations for the EVENTS table
 */

function getAllEvents(role) {
  const allowed = visibilityForRole(role || null)
  return readSheet(SHEET_NAMES.EVENTS)
    .filter(e => !e.deleted_at && allowed.includes(e.visibility))
    .sort((a, b) => String(a.planned_time).localeCompare(String(b.planned_time)))
}

function getEventsByDate(date, role) {
  const allowed = visibilityForRole(role || null)
  return readSheet(SHEET_NAMES.EVENTS)
    .filter(e => e.date === date && !e.deleted_at && allowed.includes(e.visibility))
    .sort((a, b) => String(a.planned_time).localeCompare(String(b.planned_time)))
}

function getEventsByOperationId(operationId, role) {
  const allowed = visibilityForRole(role || null)
  return readSheet(SHEET_NAMES.EVENTS)
    .filter(e => e.operation_id === operationId && !e.deleted_at && allowed.includes(e.visibility))
    .sort((a, b) => String(a.planned_time).localeCompare(String(b.planned_time)))
}

function createEvent(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date().toISOString()
    const event = {
      id:           data.id           || 'EVT-' + Date.now(),
      operation_id: data.operation_id || '',
      date:         data.date         || '',
      planned_time: data.planned_time || '',
      actual_time:  data.actual_time  || '',
      end_time:     data.end_time     || '',
      title:        data.title        || '',
      status:       data.status       || 'upcoming',
      type:         data.type         || 'briefing',
      detail:       data.detail       || '',
      reporter:     data.reporter     || '',
      location:     data.location     || '',
      duration:     data.duration     || 30,
      priority:     data.priority     || 'normal',
      visibility:   data.visibility   || 'public',
      deleted_at:   '',
      deleted_by:   '',
      created_at:   now,
      updated_at:   now,
    }
    appendRow(SHEET_NAMES.EVENTS, event)
    return event
  } finally {
    lock.releaseLock()
  }
}

function updateEvent(id, updates) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const ok = updateRowById(SHEET_NAMES.EVENTS, id, {
      ...updates,
      updated_at: new Date().toISOString(),
    })
    return { ok }
  } finally {
    lock.releaseLock()
  }
}

function bulkCreateEvents(operationId, defaultDate, eventsArray) {
  const lock = LockService.getScriptLock()
  lock.waitLock(10000)
  try {
    const sheet   = getOrCreateSheet(SHEET_NAMES.EVENTS)
    const headers = HEADERS[SHEET_NAMES.EVENTS]
    const now     = new Date().toISOString()
    const created = []

    const rows = eventsArray.map((data, i) => {
      const event = {
        id:           'EVT-' + Date.now() + '-' + i,
        operation_id: operationId,
        date:         data.date         || defaultDate || '',
        planned_time: data.planned_time || '',
        actual_time:  data.actual_time  || '',
        end_time:     data.end_time     || '',
        title:        data.title        || '',
        status:       data.status       || 'upcoming',
        type:         data.type         || 'briefing',
        detail:       data.detail       || '',
        reporter:     data.reporter     || '',
        location:     data.location     || '',
        duration:     data.duration     !== undefined ? data.duration : 30,
        priority:     data.priority     || 'normal',
        visibility:   data.visibility   || 'public',
        deleted_at:   '',
        deleted_by:   '',
        created_at:   now,
        updated_at:   now,
      }
      created.push(event)
      return headers.map(h => (event[h] !== undefined && event[h] !== null) ? event[h] : '')
    })

    if (rows.length > 0) {
      const startRow = sheet.getLastRow() + 1
      sheet.getRange(startRow, 1, rows.length, headers.length).setValues(rows)
    }

    return created
  } finally {
    lock.releaseLock()
  }
}

function deleteEvent(id, deletedBy) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const ok = updateRowById(SHEET_NAMES.EVENTS, id, {
      deleted_at: new Date().toISOString(),
      deleted_by: deletedBy || 'admin',
      updated_at: new Date().toISOString(),
    })
    return { ok }
  } finally {
    lock.releaseLock()
  }
}

function restoreEvent(id) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const ok = updateRowById(SHEET_NAMES.EVENTS, id, {
      deleted_at: '',
      deleted_by: '',
      updated_at: new Date().toISOString(),
    })
    return { ok }
  } finally {
    lock.releaseLock()
  }
}

function getDeletedEvents() {
  return readSheet(SHEET_NAMES.EVENTS)
    .filter(e => !!e.deleted_at)
    .sort((a, b) => String(b.deleted_at).localeCompare(String(a.deleted_at)))
}
