/**
 * Users.gs — USERS table (future authentication layer)
 *
 * Placeholder for role-based access: admin vs viewer.
 * PIN-based auth can be layered here once needed.
 */

/**
 * Validates a user PIN (stub — always false until implemented).
 * @param {string} userId
 * @param {string} pin
 * @returns {{ ok: boolean, role: string|null }}
 */
function validateUser(userId, pin) {
  const users = readSheet(SHEET_NAMES.USERS)
  const user  = users.find(u => u.id === userId)
  if (!user) return { ok: false, role: null }
  // TODO: compare hashed PIN
  return { ok: user.pin_hash === pin, role: user.role || 'viewer' }
}

/**
 * Returns the role for a given userId without PIN check.
 * Used for display/filter logic only.
 * @param {string} userId
 * @returns {string}
 */
function getUserRole(userId) {
  const users = readSheet(SHEET_NAMES.USERS)
  const user  = users.find(u => u.id === userId)
  return user ? user.role : 'viewer'
}
