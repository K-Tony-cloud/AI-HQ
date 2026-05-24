/**
 * Attachments.gs — Google Drive upload + EVENT_ATTACHMENTS CRUD
 *
 * Required Script Property:
 *   DRIVE_FOLDER_ID = Google Drive folder ID for all op attachments
 *   (if not set, files are uploaded to the script owner's My Drive root)
 */

function getDriveRoot() {
  const id = PropertiesService.getScriptProperties().getProperty('DRIVE_FOLDER_ID')
  return id ? DriveApp.getFolderById(id) : DriveApp.getRootFolder()
}

function getOrCreateSubfolder(parent, name) {
  const it = parent.getFoldersByName(name)
  return it.hasNext() ? it.next() : parent.createFolder(name)
}

/* ── Upload base64-encoded file to Drive ─────────────────────── */
function uploadFileToDrive(operationId, fileName, base64Data, mimeType) {
  const root     = getDriveRoot()
  const opFolder = getOrCreateSubfolder(root, operationId || 'general')
  const bytes    = Utilities.base64Decode(base64Data)
  const blob     = Utilities.newBlob(bytes, mimeType, fileName)
  const file     = opFolder.createFile(blob)
  file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW)
  return {
    fileId:  file.getId(),
    fileUrl: 'https://drive.google.com/file/d/' + file.getId() + '/view',
  }
}

/* ── Create attachment record ─────────────────────────────────── */
function createAttachment(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(10000)
  try {
    const { operationId, eventId, fileName, fileData, mimeType, uploadedBy } = data
    if (!eventId)  throw new Error('eventId is required')
    if (!fileData) throw new Error('fileData is required')

    const uploaded = uploadFileToDrive(operationId, fileName || 'attachment', fileData, mimeType || 'application/octet-stream')

    const record = {
      attachment_id: 'ATT-' + Date.now(),
      operation_id:  operationId || '',
      event_id:      eventId,
      file_name:     fileName    || 'attachment',
      file_url:      uploaded.fileUrl,
      file_type:     mimeType    || 'application/octet-stream',
      uploaded_by:   uploadedBy  || 'ADMIN',
      uploaded_at:   new Date().toISOString(),
    }
    appendRow(SHEET_NAMES.ATTACHMENTS, record)
    return record
  } finally {
    lock.releaseLock()
  }
}

/* ── Query ────────────────────────────────────────────────────── */
function getAttachmentsByEventId(eventId) {
  return readSheet(SHEET_NAMES.ATTACHMENTS).filter(a => a.event_id === eventId)
}
