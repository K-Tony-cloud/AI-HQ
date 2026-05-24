/**
 * Schema.gs — Sheet initialization, column definitions, and read helpers
 */

const SHEET_NAMES = {
  OPERATIONS:  'operations',
  EVENTS:      'events',
  LOGS:        'event_logs',
  ATTACHMENTS: 'event_attachments',
  META:        'operation_meta',
  USERS:       'users',
}

const HEADERS = {
  operations: [
    'id', 'title', 'date', 'classification', 'commander',
    'start_time', 'end_time', 'venue', 'status', 'created_at', 'updated_at',
  ],
  events: [
    'id', 'operation_id', 'date', 'planned_time', 'actual_time', 'end_time',
    'title', 'status', 'type', 'detail', 'reporter',
    'location', 'duration', 'priority', 'created_at', 'updated_at',
  ],
  event_logs: [
    'id', 'operation_id', 'event_id', 'time', 'message', 'user', 'type', 'created_at',
  ],
  event_attachments: [
    'attachment_id', 'operation_id', 'event_id', 'file_name',
    'file_url', 'file_type', 'uploaded_by', 'uploaded_at',
  ],
  operation_meta: [
    'id', 'name', 'date', 'classification', 'commander',
    'start_time', 'end_time', 'venue', 'status', 'updated_at',
  ],
  users: [
    'id', 'name', 'role', 'email', 'pin_hash', 'created_at',
  ],
}

/* ── Spreadsheet accessor ─────────────────────────────────────── */

function getSpreadsheet() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID')
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet()
}

function getOrCreateSheet(name) {
  const ss    = getSpreadsheet()
  let   sheet = ss.getSheetByName(name)
  if (!sheet) sheet = ss.insertSheet(name)
  return sheet
}

/* ── Value formatter ──────────────────────────────────────────────
   Google Sheets auto-converts "09:00" → Date (epoch 1899-12-30)
   and "2026-05-22" → Date. Convert back to clean strings.
─────────────────────────────────────────────────────────────────── */
function formatValue(value) {
  if (value === '' || value === null || value === undefined) return null
  if (!(value instanceof Date)) return value

  const y = value.getFullYear()
  if (y <= 1900) {
    return String(value.getHours()).padStart(2, '0') + ':' +
           String(value.getMinutes()).padStart(2, '0')
  }
  const mm = String(value.getMonth() + 1).padStart(2, '0')
  const dd = String(value.getDate()).padStart(2, '0')
  return `${y}-${mm}-${dd}`
}

/* ── Sheet I/O ────────────────────────────────────────────────── */

function readSheet(sheetName) {
  const sheet  = getOrCreateSheet(sheetName)
  const values = sheet.getDataRange().getValues()
  if (values.length < 2) return []
  const headers = values[0]
  return values.slice(1).map(row =>
    Object.fromEntries(headers.map((h, i) => [h, formatValue(row[i])]))
  )
}

function appendRow(sheetName, obj) {
  const sheet   = getOrCreateSheet(sheetName)
  const headers = HEADERS[sheetName]
  const row     = headers.map(h => (obj[h] !== undefined && obj[h] !== null) ? obj[h] : '')
  sheet.appendRow(row)
}

function updateRowById(sheetName, id, updates) {
  const sheet   = getOrCreateSheet(sheetName)
  const headers = HEADERS[sheetName]
  const data    = sheet.getDataRange().getValues()
  const idCol   = headers.indexOf('id')

  for (let i = 1; i < data.length; i++) {
    if (String(data[i][idCol]) === String(id)) {
      headers.forEach((h, j) => {
        if (updates[h] !== undefined) sheet.getRange(i + 1, j + 1).setValue(updates[h])
      })
      return true
    }
  }
  return false
}

/* ── Schema repair helpers (run from editor, not web app) ─────── */

// Call from the editor: fixes missing/shifted headers in event_attachments and event_logs
// without deleting existing data.
function fixAttachments() {
  _ensureSheetHeaders('event_attachments')
  Logger.log('Done. Check the event_attachments sheet.')
}

function diagSheets() {
  ['event_logs', 'event_attachments'].forEach(name => {
    const sheet = getSpreadsheet().getSheetByName(name)
    if (!sheet) { Logger.log(name + ': SHEET MISSING'); return }
    const rows = sheet.getDataRange().getValues()
    Logger.log(name + ' row count: ' + rows.length)
    if (rows.length > 0) Logger.log(name + ' header row: ' + JSON.stringify(rows[0]))
    if (rows.length > 1) Logger.log(name + ' data row 1: ' + JSON.stringify(rows[1]))
  })
}

function _ensureSheetHeaders(sheetName) {
  const expected = HEADERS[sheetName]
  const sheet    = getOrCreateSheet(sheetName)
  const lastRow  = sheet.getLastRow()

  if (lastRow === 0) {
    sheet.appendRow(expected)
    sheet.getRange(1, 1, 1, expected.length).setFontWeight('bold').setBackground('#f0f4ff')
    Logger.log(sheetName + ': was empty, headers added')
    return
  }

  const firstRowVals = sheet.getRange(1, 1, 1, Math.max(expected.length, sheet.getLastColumn())).getValues()[0]
  if (firstRowVals[0] === expected[0]) {
    Logger.log(sheetName + ': headers OK → ' + firstRowVals.join(', '))
    return
  }

  // Header row is missing — insert at row 1, shift data down
  sheet.insertRowBefore(1)
  sheet.getRange(1, 1, 1, expected.length)
    .setValues([expected])
    .setFontWeight('bold')
    .setBackground('#f0f4ff')
  Logger.log(sheetName + ': missing headers, inserted. First data row now at row 2.')
}

/* ── Schema init ──────────────────────────────────────────────── */

function initSchema() {
  Object.entries(HEADERS).forEach(([name, headers]) => {
    const sheet = getOrCreateSheet(name)
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(headers)
      sheet.getRange(1, 1, 1, headers.length)
        .setFontWeight('bold')
        .setBackground('#f0f4ff')
    }
  })
  Logger.log('Schema initialized')
}

function resetAll() {
  Logger.log('Starting full reset...')
  const sheetList = [
    SHEET_NAMES.OPERATIONS, SHEET_NAMES.EVENTS,
    SHEET_NAMES.LOGS, SHEET_NAMES.ATTACHMENTS, SHEET_NAMES.META, SHEET_NAMES.USERS,
  ]
  sheetList.forEach(name => {
    const sheet = getOrCreateSheet(name)
    const last  = sheet.getLastRow()
    if (last > 0) sheet.deleteRows(1, last)
    Logger.log('Cleared: ' + name)
  })
  initSchema()
  seedAll()
  Logger.log('Reset complete.')
}

function forceReset() {
  Logger.log('Starting force reset...')
  const ss = getSpreadsheet()
  const sheetList = [
    SHEET_NAMES.OPERATIONS, SHEET_NAMES.EVENTS,
    SHEET_NAMES.LOGS, SHEET_NAMES.ATTACHMENTS, SHEET_NAMES.META, SHEET_NAMES.USERS,
  ]
  sheetList.forEach(name => {
    const sheet = ss.getSheetByName(name) || ss.insertSheet(name)
    sheet.clear()
    Logger.log('Cleared: ' + name)
  })
  initSchema()
  seedAll()
  Logger.log('Force reset complete.')
}
