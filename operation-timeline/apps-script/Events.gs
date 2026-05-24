/**
 * Events.gs — CRUD operations for the EVENTS table
 */

function getAllEvents() {
  return readSheet(SHEET_NAMES.EVENTS).sort((a, b) =>
    String(a.planned_time).localeCompare(String(b.planned_time))
  )
}

function getEventsByDate(date) {
  return getAllEvents().filter(e => e.date === date)
}

function getEventsByOperationId(operationId) {
  return getAllEvents().filter(e => e.operation_id === operationId)
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
