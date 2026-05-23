/**
 * Schema.gs — Sheet initialization, column definitions, and read helpers
 *
 * Run resetAll() to fully reset and re-seed the spreadsheet from scratch.
 * Run initSchema() alone to create headers without touching data.
 */

const SHEET_NAMES = {
  EVENTS:    'events',
  LOGS:      'event_logs',
  META:      'operation_meta',
  USERS:     'users',
}

const HEADERS = {
  events: [
    'id', 'date', 'planned_time', 'actual_time', 'end_time',
    'title', 'status', 'type', 'detail', 'reporter',
    'location', 'duration', 'priority', 'created_at', 'updated_at',
  ],
  event_logs: [
    'id', 'event_id', 'time', 'message', 'user', 'type', 'created_at',
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
    // Time-only value: Sheets stores as 1899-12-30 epoch
    return String(value.getHours()).padStart(2, '0') + ':' +
           String(value.getMinutes()).padStart(2, '0')
  }
  // Regular date: use LOCAL parts to avoid UTC midnight shift
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

/* ── Schema init ──────────────────────────────────────────────── */

/**
 * Creates each sheet and writes the header row if the sheet is empty.
 * Safe to re-run — only writes headers to completely empty sheets.
 */
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

/**
 * Wipes ALL rows (including headers) from every sheet,
 * re-creates headers via initSchema, then re-seeds all data.
 * USE WITH CAUTION — destroys all existing data.
 */
function resetAll() {
  Logger.log('Starting full reset...')
  const sheetList = [SHEET_NAMES.EVENTS, SHEET_NAMES.LOGS, SHEET_NAMES.META, SHEET_NAMES.USERS]
  sheetList.forEach(name => {
    const sheet = getOrCreateSheet(name)
    const last  = sheet.getLastRow()
    if (last > 0) sheet.deleteRows(1, last)
    Logger.log('Cleared: ' + name)
  })
  initSchema()
  seedAll()
  Logger.log('Reset complete — all sheets initialized and seeded.')
}

/**
 * Alternative to resetAll() — uses sheet.clear() instead of deleteRows.
 * Use this if resetAll() silently fails (e.g. frozen rows, protected ranges).
 */
function forceReset() {
  Logger.log('Starting force reset...')
  const ss        = getSpreadsheet()
  const sheetList = [SHEET_NAMES.EVENTS, SHEET_NAMES.LOGS, SHEET_NAMES.META, SHEET_NAMES.USERS]
  sheetList.forEach(name => {
    const sheet = ss.getSheetByName(name) || ss.insertSheet(name)
    sheet.clear()
    Logger.log('Cleared: ' + name)
  })
  initSchema()
  seedAll()
  Logger.log('Force reset complete.')
}
