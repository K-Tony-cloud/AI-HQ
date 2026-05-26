/**
 * Users.gs — PIN-based authentication and user management
 *
 * Auth flow:
 *   1. POST {action:'loginPin', pin:'1234'} → GAS hashes PIN, looks up user
 *   2. Returns {ok, role, token, name, operation_scope}
 *   3. Frontend stores token in sessionStorage
 *   4. All subsequent requests include token param
 *   5. GAS validates token on each write/restricted action
 *
 * Roles: op_admin | super_admin  (no token = public viewer)
 * Token expiry: 8 hours
 * operation_scope: '*' = all operations, or comma-separated op IDs
 */

const TOKEN_TTL_MS = 8 * 60 * 60 * 1000  // 8 hours

function _hashPin(pin) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(pin))
  return bytes.map(b => ('0' + (b & 0xff).toString(16)).slice(-2)).join('')
}

function loginWithPin(pin) {
  if (!pin) return { ok: false, error: 'PIN required' }
  const hash  = _hashPin(pin)

  const sheet = getOrCreateSheet(SHEET_NAMES.USERS)
  const data  = sheet.getDataRange().getValues()
  if (data.length < 2) return { ok: false, error: 'Access denied' }

  const headers         = data[0]
  const pinHashIdx      = headers.indexOf('pin_hash')
  const activeIdx       = headers.indexOf('active')
  const roleIdx         = headers.indexOf('role')
  const nameIdx         = headers.indexOf('name')
  const scopeIdx        = headers.indexOf('operation_scope')
  const tokenIdx        = headers.indexOf('token')
  const tokenCreatedIdx = headers.indexOf('token_created')

  let userRow = -1
  for (let i = 1; i < data.length; i++) {
    if (data[i][pinHashIdx] === hash &&
        String(data[i][activeIdx]).toLowerCase() === 'true') {
      userRow = i
      break
    }
  }
  if (userRow === -1) return { ok: false, error: 'PIN ไม่ถูกต้อง' }

  const role            = data[userRow][roleIdx]           || 'op_admin'
  const name            = data[userRow][nameIdx]           || 'Admin'
  const operation_scope = data[userRow][scopeIdx]          || '*'
  const token           = Utilities.getUuid()
  const created         = new Date().toISOString()

  sheet.getRange(userRow + 1, tokenIdx + 1).setValue(token)
  sheet.getRange(userRow + 1, tokenCreatedIdx + 1).setValue(created)

  return { ok: true, role, token, name, operation_scope }
}

function validateToken(token) {
  if (!token) return null
  const users = readSheet(SHEET_NAMES.USERS)
  const user  = users.find(u => u.token === token)
  if (!user) return null
  if (String(user.active).toLowerCase() !== 'true') return null

  if (user.token_created) {
    const created = new Date(user.token_created).getTime()
    if (Date.now() - created > TOKEN_TTL_MS) {
      _clearToken(token)
      return null
    }
  }
  return {
    role:            user.role            || 'op_admin',
    name:            user.name            || '',
    operation_scope: user.operation_scope || '*',
  }
}

function logoutToken(token) {
  if (!token) return false
  return _clearToken(token)
}

function _clearToken(token) {
  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]
  const tokenIdx        = headers.indexOf('token')
  const tokenCreatedIdx = headers.indexOf('token_created')
  for (let i = 1; i < data.length; i++) {
    if (data[i][tokenIdx] === token) {
      sheet.getRange(i + 1, tokenIdx + 1).setValue('')
      sheet.getRange(i + 1, tokenCreatedIdx + 1).setValue('')
      return true
    }
  }
  return false
}

function listUsers() {
  return readSheet(SHEET_NAMES.USERS).map(u => ({
    id:              u.id,
    name:            u.name,
    role:            u.role,
    operation_scope: u.operation_scope,
    active:          u.active,
    created_at:      u.created_at,
  }))
}

function addUser(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date().toISOString()
    const user = {
      id:              'USR-' + Date.now(),
      name:            data.name            || '',
      role:            data.role            || 'op_admin',
      pin_hash:        data.pin ? _hashPin(data.pin) : '',
      operation_scope: data.operation_scope || '*',
      active:          'true',
      token:           '',
      token_created:   '',
      created_at:      now,
    }
    appendRow(SHEET_NAMES.USERS, user)
    return { id: user.id, name: user.name, role: user.role, operation_scope: user.operation_scope, active: user.active, created_at: user.created_at }
  } finally {
    lock.releaseLock()
  }
}

function removeUser(id) {
  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]
  const idIdx     = headers.indexOf('id')
  const activeIdx = headers.indexOf('active')
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][idIdx]) === String(id)) {
      sheet.getRange(i + 1, activeIdx + 1).setValue('false')
      return true
    }
  }
  return false
}

/**
 * seedAdminPin — run once from the Apps Script function dropdown to create
 * the first super admin row and set their PIN.
 *
 * Safe to run multiple times:
 *   - If USR-001 already exists, only the PIN hash is updated.
 *   - PIN is always hashed through _hashPin() — never stored as plain text.
 *   - Change the PIN later by calling setPin('USR-001', 'newpin') from the editor.
 */
function seedAdminPin() {
  const SEED_ID    = 'USR-001'
  const SEED_PIN   = '1234'       // ← change before running if desired
  const SEED_NAME  = 'Super Admin'
  const SEED_ROLE  = 'super_admin'
  const SEED_SCOPE = '*'

  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data.length > 0 ? data[0] : []

  // If sheet is empty, initialise headers first
  if (headers.length === 0 || headers[0] !== 'id') {
    initSchema()
    Logger.log('Schema initialised.')
  }

  // Re-read after potential init
  const fresh   = sheet.getDataRange().getValues()
  const hdrs    = fresh[0]
  const idIdx   = hdrs.indexOf('id')

  // Check if USR-001 already exists
  let existingRow = -1
  for (let i = 1; i < fresh.length; i++) {
    if (String(fresh[i][idIdx]) === SEED_ID) { existingRow = i; break }
  }

  if (existingRow === -1) {
    // Create the row
    const now = new Date().toISOString()
    const user = {
      id:              SEED_ID,
      name:            SEED_NAME,
      role:            SEED_ROLE,
      pin_hash:        _hashPin(SEED_PIN),
      operation_scope: SEED_SCOPE,
      active:          'true',
      token:           '',
      token_created:   '',
      created_at:      now,
    }
    appendRow(SHEET_NAMES.USERS, user)
    Logger.log('Created super admin row: ' + SEED_ID)
  } else {
    // Row exists — only update pin_hash
    const pinHashIdx = hdrs.indexOf('pin_hash')
    sheet.getRange(existingRow + 1, pinHashIdx + 1).setValue(_hashPin(SEED_PIN))
    Logger.log('Updated PIN for existing user: ' + SEED_ID)
  }

  Logger.log('Done. Login with PIN: ' + SEED_PIN)
  Logger.log('Change PIN later: setPin("USR-001", "yourNewPin")')
}

// Run from GAS editor to set/reset a user's PIN by their id
function setPin(userId, pin) {
  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]
  const idIdx      = headers.indexOf('id')
  const pinHashIdx = headers.indexOf('pin_hash')
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][idIdx]) === String(userId)) {
      sheet.getRange(i + 1, pinHashIdx + 1).setValue(_hashPin(pin))
      Logger.log('PIN updated for user: ' + userId)
      return
    }
  }
  Logger.log('User not found: ' + userId)
}

// Returns allowed visibility levels for a given role
// null / '' = legacy events with no visibility set → default to public
function visibilityForRole(role) {
  if (role === 'super_admin') return ['public', 'internal', 'restricted', null, '']
  if (role === 'op_admin')   return ['public', 'internal', null, '']
  return ['public', null, '']
}
