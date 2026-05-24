/**
 * Attachments.gs — Google Drive upload + EVENT_ATTACHMENTS CRUD
 *
 * Required Script Property:
 *   DRIVE_FOLDER_ID = Google Drive folder ID for "Operation Timeline Uploads"
 *
 * Folder structure:
 *   Operation Timeline Uploads/          ← DRIVE_FOLDER_ID points here
 *   └── OP-XXX_OperationName_Date/       ← auto-created per operation
 *       └── uploaded files...
 */

function getDriveRoot() {
  const id = PropertiesService.getScriptProperties().getProperty('DRIVE_FOLDER_ID')
  if (!id) throw new Error('DRIVE_FOLDER_ID script property is not set. Create a dedicated "Operation Timeline Uploads" folder in Drive and paste its ID into Script Properties.')
  return DriveApp.getFolderById(id)
}

function getOrCreateSubfolder(parent, name) {
  const it = parent.getFoldersByName(name)
  return it.hasNext() ? it.next() : parent.createFolder(name)
}

function buildOperationFolderName(operationId, operationTitle, operationDate) {
  if (!operationId) throw new Error('operationId is required for folder naming')
  const safeName = (operationTitle || '')
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '_')
    .trim()
    .slice(0, 40)
  const safeDate = (operationDate || '').replace(/[^\d-]/g, '').slice(0, 10)
  const name = [operationId, safeName, safeDate].filter(Boolean).join('_')
  if (!name) throw new Error('Could not build a valid folder name for operation: ' + operationId)
  return name
}

/* ── Diagnostic: run from editor to verify folder setup ──────── */
function diagFolders() {
  const folderId = PropertiesService.getScriptProperties().getProperty('DRIVE_FOLDER_ID')
  Logger.log('DRIVE_FOLDER_ID from properties: ' + folderId)
  if (!folderId) { Logger.log('ERROR: DRIVE_FOLDER_ID not set'); return }
  const root = DriveApp.getFolderById(folderId)
  Logger.log('Root folder name: ' + root.getName() + ' | id: ' + root.getId())
  const it = root.getFolders()
  Logger.log('Subfolders inside root:')
  while (it.hasNext()) { const f = it.next(); Logger.log('  ' + f.getName() + ' | ' + f.getId()) }
}

/* ── Upload base64-encoded file to Drive ─────────────────────── */
function uploadFileToDrive(operationId, operationTitle, operationDate, fileName, base64Data, mimeType) {
  const root       = getDriveRoot()
  const folderName = buildOperationFolderName(operationId, operationTitle, operationDate)
  const opFolder   = getOrCreateSubfolder(root, folderName)
  const bytes      = Utilities.base64Decode(base64Data)
  const blob       = Utilities.newBlob(bytes, mimeType, fileName)
  const file       = opFolder.createFile(blob)
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
    const {
      operationId, operationTitle, operationDate,
      eventId, fileName, fileData, mimeType, uploadedBy,
    } = data

    if (!operationId) throw new Error('operationId is required')
    if (!eventId)     throw new Error('eventId is required')
    if (!fileData)    throw new Error('fileData is required')

    const uploaded = uploadFileToDrive(
      operationId,
      operationTitle || '',
      operationDate  || '',
      fileName       || 'attachment',
      fileData,
      mimeType       || 'application/octet-stream',
    )

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
