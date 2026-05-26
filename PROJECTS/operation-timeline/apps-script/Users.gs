/**
 * Users.gs — Authentication and user management
 *
 * Auth flow:
 *   1. Frontend does Google OAuth → gets credential (JWT)
 *   2. POST {action:'loginGoogle', credential:'...'} → GAS verifies via tokeninfo API
 *   3. GAS looks up email in Users sheet → returns {role, token}
 *   4. Frontend sends token in all subsequent requests
 *   5. GAS validates token on each request
 *
 * Roles: op_admin | super_admin  (no token = public viewer)
 * Token expiry: 8 hours
 */

const TOKEN_TTL_MS = 8 * 60 * 60 * 1000  // 8 hours

function loginWithGoogle(credential) {
  // Verify credential via Google tokeninfo endpoint
  const url = 'https://oauth2.googleapis.com/tokeninfo?id_token=' + encodeURIComponent(credential)
  let info
  try {
    const res  = UrlFetchApp.fetch(url, { muteHttpExceptions: true })
    const code = res.getResponseCode()
    if (code !== 200) return { ok: false, error: 'Invalid credential' }
    info = JSON.parse(res.getContentText())
  } catch (ex) {
    return { ok: false, error: 'Token verification failed: ' + ex.message }
  }

  const email = info.email
  if (!email) return { ok: false, error: 'No email in token' }

  // Look up user in sheet
  const sheet = getOrCreateSheet(SHEET_NAMES.USERS)
  const data  = sheet.getDataRange().getValues()
  if (data.length < 2) return { ok: false, error: 'Access denied' }

  const headers = data[0]
  const emailIdx = headers.indexOf('email')
  const activeIdx = headers.indexOf('active')
  const roleIdx   = headers.indexOf('role')
  const nameIdx   = headers.indexOf('name')
  const tokenIdx  = headers.indexOf('token')
  const tokenCreatedIdx = headers.indexOf('token_created')

  let userRow = -1
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][emailIdx]).toLowerCase() === email.toLowerCase() &&
        String(data[i][activeIdx]).toLowerCase() === 'true') {
      userRow = i
      break
    }
  }
  if (userRow === -1) return { ok: false, error: 'Access denied' }

  const role = data[userRow][roleIdx] || 'op_admin'
  const name = data[userRow][nameIdx] || info.name || email

  // Generate session token
  const token   = Utilities.getUuid()
  const created = new Date().toISOString()

  sheet.getRange(userRow + 1, tokenIdx + 1).setValue(token)
  sheet.getRange(userRow + 1, tokenCreatedIdx + 1).setValue(created)

  return { ok: true, role, token, name, email }
}

function validateToken(token) {
  if (!token) return null
  const users = readSheet(SHEET_NAMES.USERS)
  const user  = users.find(u => u.token === token)
  if (!user) return null
  if (String(user.active).toLowerCase() !== 'true') return null

  // Check expiry
  if (user.token_created) {
    const created = new Date(user.token_created).getTime()
    if (Date.now() - created > TOKEN_TTL_MS) {
      // Expired — clear token
      _clearToken(token)
      return null
    }
  }
  return { role: user.role || 'op_admin', email: user.email, name: user.name }
}

function logoutToken(token) {
  if (!token) return false
  return _clearToken(token)
}

function _clearToken(token) {
  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]
  const tokenIdx = headers.indexOf('token')
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
    id:      u.id,
    name:    u.name,
    email:   u.email,
    role:    u.role,
    active:  u.active,
    created_at: u.created_at,
  }))
}

function addUser(data) {
  const lock = LockService.getScriptLock()
  lock.waitLock(5000)
  try {
    const now = new Date().toISOString()
    const user = {
      id:            'USR-' + Date.now(),
      name:          data.name  || '',
      role:          data.role  || 'op_admin',
      email:         (data.email || '').toLowerCase(),
      active:        'true',
      token:         '',
      token_created: '',
      created_at:    now,
    }
    appendRow(SHEET_NAMES.USERS, user)
    return user
  } finally {
    lock.releaseLock()
  }
}

function removeUser(email) {
  const sheet   = getOrCreateSheet(SHEET_NAMES.USERS)
  const data    = sheet.getDataRange().getValues()
  const headers = data[0]
  const emailIdx  = headers.indexOf('email')
  const activeIdx = headers.indexOf('active')
  for (let i = 1; i < data.length; i++) {
    if (String(data[i][emailIdx]).toLowerCase() === email.toLowerCase()) {
      sheet.getRange(i + 1, activeIdx + 1).setValue('false')
      return true
    }
  }
  return false
}

// Returns allowed visibility levels for a given role
function visibilityForRole(role) {
  if (role === 'super_admin') return ['public', 'internal', 'restricted', 'needs_review', null, '']
  if (role === 'op_admin')    return ['public', 'internal', null, '']
  return ['public', null, '']  // public viewer — null/empty = legacy events shown as public
}
