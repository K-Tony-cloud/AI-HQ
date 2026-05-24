/**
 * Operations.gs — CRUD for the OPERATIONS table
 */

function getAllOperations() {
  return readSheet(SHEET_NAMES.OPERATIONS).sort((a, b) =>
    String(b.date || '').localeCompare(String(a.date || ''))
  )
}

function getOperationById(id) {
  return readSheet(SHEET_NAMES.OPERATIONS).find(o => o.id === id) || null
}

function createOperation(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date().toISOString()
    const op = {
      id:             data.id             || 'OP-' + Date.now(),
      title:          data.title          || '',
      date:           data.date           || '',
      classification: data.classification || 'RESTRICTED',
      commander:      data.commander      || '',
      start_time:     data.start_time     || '09:00',
      end_time:       data.end_time       || '20:00',
      venue:          data.venue          || '',
      status:         data.status         || 'ACTIVE',
      created_at:     now,
      updated_at:     now,
    }
    appendRow(SHEET_NAMES.OPERATIONS, op)
    return op
  } finally {
    lock.releaseLock()
  }
}

function updateOperation(id, updates) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const ok = updateRowById(SHEET_NAMES.OPERATIONS, id, {
      ...updates,
      updated_at: new Date().toISOString(),
    })
    return { ok }
  } finally {
    lock.releaseLock()
  }
}

/**
 * Clones an operation and all its events into a new operation.
 * @param {string} sourceId  ID of the operation to clone
 * @param {Object} newData   Overrides for the new operation (title, date, etc.)
 */
function cloneOperation(sourceId, newData) {
  const lock = LockService.getScriptLock()
  lock.waitLock(10000)
  try {
    const source = getOperationById(sourceId)
    if (!source) throw new Error('Source operation not found: ' + sourceId)

    const now     = new Date().toISOString()
    const newOpId = 'OP-' + Date.now()
    const newOp   = {
      id:             newOpId,
      title:          newData.title          || (source.title + ' (Clone)'),
      date:           newData.date           || '',
      classification: newData.classification || source.classification,
      commander:      newData.commander      || source.commander,
      start_time:     newData.start_time     || source.start_time,
      end_time:       newData.end_time       || source.end_time,
      venue:          newData.venue          || source.venue,
      status:         'ACTIVE',
      created_at:     now,
      updated_at:     now,
    }
    appendRow(SHEET_NAMES.OPERATIONS, newOp)

    // Clone events — reset status/actual times
    const sourceEvents = getEventsByOperationId(sourceId)
    sourceEvents.forEach((ev, i) => {
      const evNow = new Date().toISOString()
      appendRow(SHEET_NAMES.EVENTS, {
        id:           'EVT-' + Date.now() + '-' + i,
        operation_id: newOpId,
        date:         newData.date || '',
        planned_time: ev.planned_time,
        actual_time:  '',
        end_time:     '',
        title:        ev.title,
        status:       'upcoming',
        type:         ev.type,
        detail:       ev.detail,
        reporter:     ev.reporter,
        location:     ev.location,
        duration:     ev.duration,
        priority:     ev.priority,
        created_at:   evNow,
        updated_at:   evNow,
      })
    })

    return newOp
  } finally {
    lock.releaseLock()
  }
}
