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
 * GET endpoints:
 *   ?action=getOperations
 *   ?action=getOperation&id=OP-xxx
 *   ?action=getEvents[&operationId=OP-xxx][&date=YYYY-MM-DD]
 *   ?action=getMeta
 *   ?action=getLogs&eventId=EVT-xxx
 *   ?action=getAllLogs[&limit=N]
 *   ?action=ping
 *
 * POST endpoints (body JSON):
 *   {action:'addOperation',    data:{...}}
 *   {action:'updateOperation', id:'OP-xxx', data:{...}}
 *   {action:'cloneOperation',  sourceId:'OP-xxx', data:{...}}
 *   {action:'addEvent',        data:{...}}
 *   {action:'updateEvent',     id:'EVT-xxx', data:{...}}
 *   {action:'addLog',          data:{...}}
 */

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
      case 'getOperations': {
        return ok(getAllOperations())
      }
      case 'getOperation': {
        const id = e.parameter.id
        if (!id) return err('id required')
        return ok(getOperationById(id))
      }
      case 'getEvents': {
        const operationId = e.parameter.operationId
        const date        = e.parameter.date
        if (operationId) return ok(getEventsByOperationId(operationId))
        if (date)        return ok(getEventsByDate(date))
        return ok(getAllEvents())
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
      case 'getAllLogs': {
        const limit = e.parameter.limit ? parseInt(e.parameter.limit) : 50
        return ok(getAllLogs(limit))
      }
      case 'ping': {
        return ok({
          status:    'ok',
          timestamp: new Date().toISOString(),
          mode:      'live',
          sheets: {
            operations: readSheet(SHEET_NAMES.OPERATIONS).length,
            events:     readSheet(SHEET_NAMES.EVENTS).length,
            logs:       readSheet(SHEET_NAMES.LOGS).length,
          },
        })
      }
      case 'forceReset': {
        forceReset()
        return ok({ reset: true, timestamp: new Date().toISOString() })
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
      case 'addOperation': {
        return ok(createOperation(payload.data || {}))
      }
      case 'updateOperation': {
        if (!payload.id) return err('id required')
        return ok(updateOperation(payload.id, payload.data || {}))
      }
      case 'cloneOperation': {
        if (!payload.sourceId) return err('sourceId required')
        return ok(cloneOperation(payload.sourceId, payload.data || {}))
      }
      case 'addEvent': {
        return ok(createEvent(payload.data || {}))
      }
      case 'updateEvent': {
        if (!payload.id) return err('id required')
        return ok(updateEvent(payload.id, payload.data || {}))
      }
      case 'addLog': {
        return ok(createLog(payload.data || {}))
      }
      default:
        return err('Unknown action: ' + action, 404)
    }
  } catch (ex) {
    return err(ex.message, 500)
  }
}
