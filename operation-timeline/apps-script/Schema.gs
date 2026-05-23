/**
 * Schema.gs — Sheet initialization and column definitions
 *
 * Run initSchema() once after creating the Google Spreadsheet.
 * Script Property "SPREADSHEET_ID" must be set before deploying as Web App.
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

/**
 * Returns the active spreadsheet (via script property or active).
 * @returns {GoogleAppsScript.Spreadsheet.Spreadsheet}
 */
function getSpreadsheet() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID')
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet()
}

/**
 * Returns a sheet by name, creating it if missing.
 * @param {string} name
 * @returns {GoogleAppsScript.Spreadsheet.Sheet}
 */
function getOrCreateSheet(name) {
  const ss    = getSpreadsheet()
  let   sheet = ss.getSheetByName(name)
  if (!sheet) sheet = ss.insertSheet(name)
  return sheet
}

/**
 * Reads all rows from a sheet and returns them as an array of objects
 * keyed by the header row.
 * @param {string} sheetName
 * @returns {Object[]}
 */
function readSheet(sheetName) {
  const sheet  = getOrCreateSheet(sheetName)
  const values = sheet.getDataRange().getValues()
  if (values.length < 2) return []
  const headers = values[0]
  return values.slice(1).map(row =>
    Object.fromEntries(headers.map((h, i) => [h, row[i] === '' ? null : row[i]]))
  )
}

/**
 * Appends a row to a sheet in header-column order.
 * @param {string} sheetName
 * @param {Object} obj
 */
function appendRow(sheetName, obj) {
  const sheet   = getOrCreateSheet(sheetName)
  const headers = HEADERS[sheetName]
  const row     = headers.map(h => obj[h] !== undefined ? obj[h] : '')
  sheet.appendRow(row)
}

/**
 * Updates a row where column 'id' matches the given id.
 * @param {string} sheetName
 * @param {string} id
 * @param {Object} updates
 * @returns {boolean} true if a row was updated
 */
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

/**
 * Run once to initialize all sheets with header rows.
 * Safe to re-run — only writes headers if the sheet is empty.
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
