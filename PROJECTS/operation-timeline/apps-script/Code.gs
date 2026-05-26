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
 *   ?action=getEvents[&operationId=OP-xxx][&date=YYYY-MM-DD][&token=TOKEN]
 *   ?action=getDeletedEvents&token=TOKEN          (super_admin only)
 *   ?action=listUsers&token=TOKEN                 (super_admin only)
 *   ?action=getMeta
 *   ?action=getLogs&eventId=EVT-xxx
 *   ?action=getAllLogs[&limit=N]
 *   ?action=getAttachments&eventId=EVT-xxx
 *   ?action=ping
 *
 * POST endpoints (body JSON):
 *   {action:'loginGoogle',     credential:'...'}
 *   {action:'logout',          token:'...'}
 *   {action:'addOperation',    data:{...}}
 *   {action:'updateOperation', id:'OP-xxx', data:{...}}
 *   {action:'cloneOperation',  sourceId:'OP-xxx', data:{...}}
 *   {action:'addEvent',        data:{...}}
 *   {action:'updateEvent',     id:'EVT-xxx', data:{...}}
 *   {action:'deleteEvent',     id:'EVT-xxx', token:'...'}          (op_admin+)
 *   {action:'restoreEvent',    id:'EVT-xxx', token:'...'}          (super_admin only)
 *   {action:'addLog',          data:{...}}
 *   {action:'importOperation', data:{operation:{...}, events:[...]}}
 *   {action:'uploadAttachment',data:{operationId, eventId, fileName, fileData, mimeType, uploadedBy}}
 *   {action:'addUser',         data:{name, email, role}, token:'...'} (super_admin only)
 *   {action:'removeUser',      email:'...', token:'...'}           (super_admin only)
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

function getCallerRole(e) {
  const token = (e && e.parameter && e.parameter.token) || ''
  if (!token) return null
  const user = validateToken(token)
  return user ? user.role : null
}

function requireRole(role, allowedRoles) {
  if (!allowedRoles.includes(role)) {
    return err('Access denied', 403)
  }
  return null
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
        const role        = getCallerRole(e)
        const operationId = e.parameter.operationId
        const date        = e.parameter.date
        if (operationId) return ok(getEventsByOperationId(operationId, role))
        if (date)        return ok(getEventsByDate(date, role))
        return ok(getAllEvents(role))
      }
      case 'getDeletedEvents': {
        const role = getCallerRole(e)
        const denied = requireRole(role, ['super_admin'])
        if (denied) return denied
        return ok(getDeletedEvents())
      }
      case 'listUsers': {
        const role = getCallerRole(e)
        const denied = requireRole(role, ['super_admin'])
        if (denied) return denied
        return ok(listUsers())
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
      case 'getAttachments': {
        const eventId = e.parameter.eventId
        if (!eventId) return err('eventId required')
        return ok(getAttachmentsByEventId(eventId))
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
      case 'testDrive': {
        try {
          const folderId = PropertiesService.getScriptProperties().getProperty('DRIVE_FOLDER_ID')
          if (!folderId) return ok({ driveOk: false, reason: 'DRIVE_FOLDER_ID not set' })
          const folder = DriveApp.getFolderById(folderId)
          return ok({ driveOk: true, folderName: folder.getName() })
        } catch (ex) {
          return ok({ driveOk: false, reason: ex.message })
        }
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
      case 'importOperation': {
        const { operation, events } = payload.data || {}
        if (!operation) return err('data.operation required')
        const op      = createOperation(operation)
        const created = events && events.length > 0
          ? bulkCreateEvents(op.id, op.date, events)
          : []
        return ok({ operation: op, events: created, count: created.length })
      }
      case 'uploadAttachment': {
        return ok(createAttachment(payload.data || {}))
      }
      case 'loginPin': {
        const pin = payload.pin
        if (!pin) return err('pin required')
        return ok(loginWithPin(pin))
      }
      case 'logout': {
        const token = payload.token
        if (!token) return err('token required')
        return ok({ loggedOut: logoutToken(token) })
      }
      case 'deleteEvent': {
        const role = validateToken(payload.token)
        if (!role) return err('Access denied', 403)
        if (!payload.id) return err('id required')
        return ok(deleteEvent(payload.id, role.email || 'admin'))
      }
      case 'restoreEvent': {
        const user = validateToken(payload.token)
        if (!user || user.role !== 'super_admin') return err('Access denied', 403)
        if (!payload.id) return err('id required')
        return ok(restoreEvent(payload.id))
      }
      case 'addUser': {
        const user = validateToken(payload.token)
        if (!user || user.role !== 'super_admin') return err('Access denied', 403)
        return ok(addUser(payload.data || {}))
      }
      case 'removeUser': {
        const user = validateToken(payload.token)
        if (!user || user.role !== 'super_admin') return err('Access denied', 403)
        if (!payload.id) return err('id required')
        return ok({ removed: removeUser(payload.id) })
      }
      default:
        return err('Unknown action: ' + action, 404)
    }
  } catch (ex) {
    return err(ex.message, 500)
  }
}
