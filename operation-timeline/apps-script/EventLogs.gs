/**
 * EventLogs.gs — CRUD operations for the EVENT_LOGS table
 */

/**
 * Returns all logs for a given eventId, sorted by time.
 * @param {string} eventId
 * @returns {Object[]}
 */
function getLogsByEventId(eventId) {
  return readSheet(SHEET_NAMES.LOGS)
    .filter(l => l.event_id === eventId)
    .sort((a, b) => String(a.time).localeCompare(String(b.time)))
}

/**
 * Returns all logs, sorted by created_at descending.
 * @param {number} [limit]  Max number of rows to return
 * @returns {Object[]}
 */
function getAllLogs(limit) {
  const all = readSheet(SHEET_NAMES.LOGS)
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  return limit ? all.slice(0, Number(limit)) : all
}

/**
 * Appends a new log entry.
 * @param {Object} data  Partial EventLog (id auto-generated)
 * @returns {Object}     The created log entry
 */
function createLog(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date()
    const log = {
      id:         data.id       || 'LOG-' + Date.now(),
      event_id:   data.event_id || '',
      time:       data.time     || `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`,
      message:    data.message  || '',
      user:       data.user     || '',
      type:       data.type     || 'update',
      created_at: now.toISOString(),
    }
    appendRow(SHEET_NAMES.LOGS, log)
    return log
  } finally {
    lock.releaseLock()
  }
}
