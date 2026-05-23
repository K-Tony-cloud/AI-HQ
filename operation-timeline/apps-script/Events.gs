/**
 * Events.gs — CRUD operations for the EVENTS table
 */

/**
 * Returns all events sorted by planned_time.
 * @returns {Object[]}
 */
function getAllEvents() {
  return readSheet(SHEET_NAMES.EVENTS).sort((a, b) =>
    String(a.planned_time).localeCompare(String(b.planned_time))
  )
}

/**
 * Returns events for a specific date.
 * @param {string} date  YYYY-MM-DD
 * @returns {Object[]}
 */
function getEventsByDate(date) {
  return getAllEvents().filter(e => e.date === date)
}

/**
 * Creates a new event row.
 * @param {Object} data  Partial OperationEvent (id auto-generated if missing)
 * @returns {Object}     The created event with id, created_at, updated_at
 */
function createEvent(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date().toISOString()
    const event = {
      id:           data.id           || 'EVT-' + Date.now(),
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

/**
 * Updates an existing event by id.
 * @param {string} id
 * @param {Object} updates  Fields to update (partial)
 * @returns {{ ok: boolean }}
 */
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
