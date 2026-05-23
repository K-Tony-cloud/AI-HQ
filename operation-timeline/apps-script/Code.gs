/**
 * Code.gs — Apps Script Web App entry point
 *
 * Deploy as Web App:
 *   Extensions → Apps Script → Deploy → New deployment
 *   Execute as: Me | Who has access: Anyone
 *
 * Set Script Properties before deploying:
 *   SPREADSHEET_ID = <your spreadsheet id>
 *
 * Endpoints:
 *   GET  ?action=getEvents[&date=YYYY-MM-DD]
 *   GET  ?action=getMeta
 *   GET  ?action=getLogs&eventId=EVT-xxx
 *   POST {action:'addEvent',    data:{...}}
 *   POST {action:'updateEvent', id:'EVT-xxx', data:{...}}
 *   POST {action:'addLog',      data:{...}}
 */

const CORS_HEADERS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Methods': 'GET, POST',
  'Access-Control-Allow-Headers': 'Content-Type',
}

function ok(payload) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, data: payload }))
    .setMimeType(ContentService.MimeType.JSON)
}

function err(message, code) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: false, error: message, code: code || 400 }))
    .setMimeType(ContentService.MimeType.JSON)
}

/* ── GET handler ─────────────────────────────────────────────── */
function doGet(e) {
  try {
    const action = e.parameter.action
    switch (action) {
      case 'getEvents': {
        const date   = e.parameter.date
        const events = date ? getEventsByDate(date) : getAllEvents()
        return ok(events)
      }
      case 'getMeta': {
        const rows = readSheet(SHEET_NAMES.META)
        return ok(rows[0] || null)
      }
      case 'getLogs': {
        const eventId = e.parameter.eventId
        if (!eventId) return err('eventId required')
        return ok(getLogsByEventId(eventId))
      }
      case 'ping': {
        return ok({
          status:    'ok',
          timestamp: new Date().toISOString(),
          mode:      'live',
          sheets: {
            events:    readSheet(SHEET_NAMES.EVENTS).length,
            logs:      readSheet(SHEET_NAMES.LOGS).length,
          },
        })
      }
      default:
        return err('Unknown action: ' + action, 404)
    }
  } catch (ex) {
    return err(ex.message, 500)
  }
}

/* ── POST handler ────────────────────────────────────────────── */
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents || '{}')
    const action  = payload.action

    switch (action) {
      case 'addEvent': {
        const event = createEvent(payload.data || {})
        return ok(event)
      }
      case 'updateEvent': {
        if (!payload.id) return err('id required')
        const result = updateEvent(payload.id, payload.data || {})
        return ok(result)
      }
      case 'addLog': {
        const log = createLog(payload.data || {})
        return ok(log)
      }
      default:
        return err('Unknown action: ' + action, 404)
    }
  } catch (ex) {
    return err(ex.message, 500)
  }
}
